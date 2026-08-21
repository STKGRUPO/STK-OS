# Relatório de Inspeção do Motor Fiscal Python — STK OS V1

**Etapa:** 3 — inspeção técnica read-only  
**Data da inspeção:** 19/08/2026  
**Status:** concluída para decisão arquitetural; não autoriza implementação, integração ou emissão  
**Documento confrontado:** `ARQUITETURA-ONLINE-SEGURANCA-STK-OS-V1.md`

## 0. Parecer executivo

O sistema fiscal localizado é um aplicativo desktop Windows/Tkinter, sem repositório Git, sem pacote Python formal, sem lockfile e com persistência em JSON/arquivos locais. A versão efetiva do módulo financeiro é **V0.3.2.2**. Existe um invólucro corporativo **V0.4**, mas ele apenas abre o financeiro preservado como subprocesso; o nome da pasta (`V031`) e `config.json` (`0.3.1`) estão defasados. O motor de cálculo se identifica internamente como V0.2/V0.2.2.

O cálculo de retenções (`fiscal_engine.py`) é pequeno, coeso, determinístico e independente da interface. A geração do DANFSe e a importação de PDF também são majoritariamente portáveis. Entretanto, montagem da DPS, assinatura, certificado, transporte HTTP, numeração, persistência e transições pós-emissão estão acoplados à classe Tkinter de `app.py` e a arquivos locais. Não há idempotência de emissão, lock de numeração, estado transacional durável, consulta/reconciliação implementada, cancelamento nem substituição.

O menor caminho seguro não é reescrever a regra fiscal e tampouco hospedar a GUI. É **extrair o comportamento fiscal validado para um serviço privado online**, preservando cálculo, mapeamentos XML e geração documental sob golden masters, mas substituindo interface, estado local, assinatura Windows insegura e transporte sem máquina de estados por fronteiras headless, persistentes e idempotentes.

Conclusões principais:

- aproximadamente **45–55% do código diretamente envolvido no fluxo fiscal já é independente de Tkinter**; após separar trechos hoje dentro de `app.py`, **70–80% do comportamento fiscal validado** pode ser preservado;
- o cálculo puro (`fiscal_engine.py`) pode ser reaproveitado quase integralmente;
- o sistema completo não é determinístico para a mesma entrada de negócio, pois usa relógio, alocação mutável de DPS e estado de interface;
- o certificado localizado é **A1/PFX**; tecnicamente A1 admite execução cloud não interativa, mas o código atual exige senha digitada por sessão e manipula a chave de modo inadequado para cloud;
- um segundo perfil de emissor usa portal web assistido, sem API/A1; esse fluxo exige usuário logado e impede operação 100% online até decisão operacional/certificado;
- existe risco crítico de duplicidade por concorrência, retry manual e timeout posterior ao envio;
- a SEFIN Nacional oferece consulta por ID da DPS, consulta por chave e eventos, mas o legado não usa essas operações;
- o diretório real mistura código, certificado, dados de clientes, bancos, logs, payloads, XMLs e PDFs de produção dentro do OneDrive.

## 1. Escopo, raiz e método seguro

### 1.1 Raízes confirmadas

| Componente | Raiz |
|---|---|
| STK OS | `C:\Users\thiag\OneDrive\Área de Trabalho\STK-OS` |
| Legado fiscal inspecionado | `C:\Users\thiag\OneDrive\Área de Trabalho\STK_Financeiro_NFSe_V031_COMPLETO\STK_Financeiro_NFSe_V031` |

O legado não está dentro do Git do STK OS e não possui `.git` próprio. Logo, “versão em uso” só pode ser identificada pelo artefato presente, hashes, marcadores internos e evidência operacional; não há commit de origem auditável.

### 1.2 Controles adotados

- nenhum entrypoint do aplicativo foi aberto;
- nenhuma chamada à SEFIN, BrasilAPI, Microsoft Graph ou portal foi executada;
- nenhum certificado/PFX foi lido, copiado ou validado;
- nenhum XML, PDF, banco, log ou JSON de cliente/emissão foi usado como fixture;
- `config.json` foi examinado apenas quanto a nomes de chaves e metadados não secretos; endpoints foram reduzidos a esquema/host;
- o secret scan estático retornou somente categorias e nomes de arquivos, nunca valores;
- somente `test_fiscal_engine.py`, isolado e sem I/O/rede, foi executado; passou em CPython 3.12.13;
- `test_cnpj_lookup.py` não executou por ausência de `requests` no ambiente isolado; nenhuma dependência foi instalada;
- `test_address_xml.py` não foi executado porque importa `app.py`, que configura arquivo de log durante o import;
- nenhum arquivo do legado foi alterado.

### 1.3 Fontes oficiais externas

A capacidade do provedor foi confirmada na documentação oficial do Sistema Nacional NFS-e, não por chamadas aos ambientes:

- [Documentação atual da NFS-e Nacional](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual/documentacao-atual);
- [Manual do contribuinte — Emissor Público API](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual/manual-contribuintes-emissor-publico-api-sistema-nacional-nfs-e-v1-2-out2025.pdf/@@download/file);
- [Manual do contribuinte — APIs do ADN](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual/manual-contribuintes-apis-adn-sistema-nacional-nfse.pdf);
- [Lista oficial de APIs de produção restrita e produção](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/apis-prod-restrita-e-producao).

## 2. Versão exata, Python e sistema operacional

### 2.1 Identificação do artefato

| Camada | Evidência | Versão caracterizada |
|---|---|---|
| Shell corporativo | `0stk_gestao.py:24`, `README_V040.txt` | V0.4 |
| Financeiro/NFS-e | título, `verAplic`, manifestos e resumos em `app.py` | **V0.3.2.2** |
| Configuração | chave `version` de `config.json` | 0.3.1, defasada |
| Consulta CNPJ | User-Agent de `cnpj_lookup.py:103` | 0.3.1, defasado |
| Motor de retenções | docstring e teste | V0.2 / teste V0.2.2 |
| Nome da pasta | diretório | V031, defasado |

**Versão operacional caracterizada:** `STK Financeiro V0.3.2.2`, anexado ao shell `STK Gestão V0.4`. A multiplicidade de versões é um risco de rastreabilidade; a migração deve usar hashes, não o nome da pasta.

Hashes SHA-256 da baseline:

| Arquivo | SHA-256 |
|---|---|
| `app.py` | `0F3F1FD0E14D8414716455266032FE8911CE0D31BC919E7E11403E3C4A594081` |
| `fiscal_engine.py` | `2F55A6C967ADA6C841EF81428FEDE95294A3DC473397F2FED9C1F9FE10DC16AF` |
| `danfse.py` | `967DF77538350387DDBC4CF2BEF903A4D2A24C1CCFAF67E47A53A59309CBB221` |
| `signer.ps1` | `3F42848FA5B9FC11DFB6737D8BA9CB7F4953F2F29B19B173E4C8B58DCAFDF944` |
| `requirements.txt` | `38D5EF5E53F956A75BDAFCBF12D1D4606912208FD45B5A7F4B39943CCCEEBE0E` |
| `0stk_gestao.py` | `11DC8F50588817ADC3AF77F28939E2BFF55B4503F3B62BFA5F669B275C5F007A` |

### 2.2 Python

- os bytecodes existentes são `*.cpython-314.pyc`, evidência de execução/compilação com **CPython 3.14**;
- não há declaração de versão mínima/máxima, `.python-version`, `pyproject.toml`, virtualenv próprio ou lockfile;
- o patch exato do CPython 3.14 não é recuperável do material;
- o teste fiscal passou também em CPython 3.12.13, mas isso não comprova a compatibilidade do aplicativo completo;
- o STK OS declara `>=3.12,<3.14`, portanto a incorporação direta em C exigiria homologar a diferença de runtime.

### 2.3 Sistema operacional

O sistema é Windows-dependente no estado atual:

- launchers `.bat` e comando `py`;
- `powershell.exe` e `signer.ps1` para XMLDSIG;
- fontes em `C:\Windows\Fonts`;
- `os.startfile`;
- tema Tk `vista`;
- alertas planejados pelo Agendador de Tarefas do Windows;
- bytecodes e artefatos estão em instalação Windows/OneDrive.

## 3. Como o programa é iniciado

| Entry point | Comportamento | Estado |
|---|---|---|
| `executar_financeiro.bat` | `py app.py` | entrada direta do financeiro; coerente |
| `app.py` | instancia `NFSeApp` e inicia `mainloop()` | emissor desktop real |
| `executar.bat` | `py stk_gestao.py` | **quebrado no artefato**: `stk_gestao.py` não existe |
| `0stk_gestao.py` | shell V0.4; abre `app.py` em subprocesso | existe, mas o launcher não aponta para ele |
| `verificar_prazos.bat` | abre alerta Tk local | exige sessão de usuário |
| `instalar.bat` | instala ranges de `requirements.txt` globalmente/no Python selecionado | não reproduzível |

O módulo fiscal não expõe CLI headless, API, fila ou função de caso de uso. O único fluxo completo de emissão é um método da classe Tkinter.

## 4. Arquitetura atual real

```text
Usuário Windows
  └─ Tkinter app.py (estado de tela + regras + orquestração)
       ├─ JSON por emissor (clientes, programações, faturamentos, DPS)
       ├─ fiscal_engine.py (cálculo puro)
       ├─ montagem DPS XML dentro de app.py
       ├─ signer.ps1 + A1/PFX (XMLDSIG)
       ├─ requests + mTLS → SEFIN Nacional
       ├─ arquivos locais (payload, resposta, XML, PDF, resumo)
       ├─ danfse.py (PDF local)
       ├─ importação assistida de DANFSe/portal
       └─ Graph delegado/interativo para e-mail

Shell V0.4 separado
  └─ SQLite stk_gestao.db para módulos ambiental/regulatório/prazos
       └─ abre app.py como outro processo
```

Não há banco transacional fiscal. O SQLite V0.4 é adicional e não substitui os JSONs financeiros, conforme o próprio `README_V040.txt`.

## 5. Mapa de módulos

| Responsabilidade | Implementação real | Observação |
|---|---|---|
| Interface fiscal | `app.py` / `NFSeApp`, `CompanyManager` | Tkinter; concentra também regras e I/O |
| Shell corporativo | `0stk_gestao.py`, `stk_modules.py` | V0.4; fora do núcleo fiscal |
| Contratos/faturamento | programações e faturamentos em `app.py:2408–3400` | não há domínio de contrato; são registros JSON de programação/lancamento |
| Retenções | `fiscal_engine.py` | módulo puro e coeso |
| Arredondamentos | `fiscal_engine.q2` | `Decimal`, `ROUND_HALF_UP`, 2 casas |
| Montagem da DPS | `app.py:_build_unsigned_dps` | dentro da classe GUI |
| Assinatura | `app.py:_sign` + `signer.ps1` | Windows/PowerShell/.NET |
| mTLS/certificado | `app.py:_mtls_cert` | converte PFX em PEM temporário sem senha |
| Comunicação SEFIN | `app.py:test_connection`, `_emit_worker` | `requests`, HTTPS, timeout e TLS habilitados |
| Consulta cadastral | `cnpj_lookup.py` | BrasilAPI; não é consulta fiscal de NFS-e |
| Consulta/reconciliação NFS-e | inexistente | provedor suporta; legado não usa |
| Cancelamento | inexistente | histórico apenas reconhece arquivo de cancelamento colocado na pasta |
| Substituição | inexistente | provedor suporta; legado não usa |
| PDFs | `danfse.py`, `danfse_pdf_import.py` | geração e importação local |
| XMLs | montagem/parse em `app.py`; render em `danfse.py` | persistidos em diretório de emissão |
| Persistência financeira | helpers JSON em `app.py` | não atômica, sem transação/lock |
| Persistência corporativa V0.4 | `stk_db.py` / SQLite | não é fonte fiscal |
| Logs e erros | `logging` em `data/app.log`, arquivos por tentativa, dialogs | sem rotação, correlação ou taxonomia operacional |
| E-mail | `graph_mail.py` + UI em `app.py` | login delegado/interativo; não pertence ao motor fiscal futuro |

## 6. Fluxo atual de emissão por API

1. Usuário seleciona emissor e ambiente na GUI.
2. Usuário informa a senha do A1 na sessão.
3. `calculate_preview` chama o motor fiscal puro.
4. `_validate` checa campos, arquivo de certificado e associação provável do CNPJ no Subject.
5. Há confirmação visual e, em produção, digitação manual de `EMITIR`.
6. Uma thread local executa `_emit_worker`.
7. `_allocate_dps` lê e sobrescreve `state.json`, incrementando o próximo número sem lock.
8. `_build_unsigned_dps` cria a DPS v1.01 e inclui timestamp atual.
9. `signer.ps1` assina por XMLDSIG usando o PFX.
10. O sistema grava XML não assinado, assinado, payload comprimido e manifesto local.
11. `requests.post` envia a DPS por HTTPS/mTLS, com timeout total de 60 s, `verify=True` e sem redirect.
12. Timeout/conexão gera arquivo `TRANSMISSAO_INDETERMINADA.txt` e bloqueio apenas instrucional.
13. Toda resposta é salva integralmente em texto; JSON também é salvo quando parseável.
14. HTTP 201 com XML compactado é tratado como autorização; demais retornos viram `RuntimeError` genérico.
15. XML autorizado e DANFSe são gravados localmente.
16. Um resumo local marca `status=emitida`.
17. A callback na GUI atualiza faturamento/programação e abre a pasta.

Pontos positivos preserváveis:

- TLS é validado (`verify=True`);
- há timeouts explícitos;
- redirects são bloqueados;
- existe manifesto pré-transmissão com hash da DPS assinada;
- o código reconhece que timeout após envio produz resultado indeterminado;
- o código distingue autorização remota de falha no pós-processamento local;
- a senha do A1 não é persistida intencionalmente.

Esses controles são úteis, mas não substituem estado durável, idempotência e reconciliação.

## 7. Fluxo atual pelo portal

Para um emissor sem A1/API, o sistema:

1. calcula e salva um rascunho local contendo dados fiscais e pessoais;
2. copia o resumo para a área de transferência;
3. abre o portal oficial no navegador;
4. exige login e conclusão manual;
5. importa posteriormente o DANFSe PDF ou registra manualmente número/chave/XML;
6. deduplica importação por chave ou combinação local de número/competência.

Esse é um fluxo humano assistido, não automação de tela. Ele depende de navegador, usuário logado e conferência manual, e não pode sustentar operação fiscal cloud 24/7 sem mudança de credencial/método do emissor.

## 8. Dependências

### 8.1 Dependências Python declaradas

`requests`, `lxml`, `cryptography`, `reportlab`, `qrcode[pil]`, `Pillow`, `msal` e `pypdf` são declaradas em ranges amplos. Não há hashes nem versões resolvidas.

Consequências:

- uma instalação futura pode receber versões diferentes da validada;
- não é possível executar auditoria de CVEs da versão real, pois a versão instalada não foi registrada;
- não há SBOM;
- extensões/nativos de `lxml`, `cryptography` e Pillow precisam ser homologados por runtime/OS;
- `msal` e Graph devem sair do serviço fiscal; entrega é responsabilidade separada no STK OS.

### 8.2 Matriz desktop/Windows

| Dependência | Existe? | Impacto |
|---|---:|---|
| Tkinter | sim | fluxo completo acoplado à GUI |
| Windows | sim | launchers, assinatura, fontes, abertura de arquivos, tema |
| COM | não encontrado | sem dependência |
| Registry | não encontrado | sem dependência |
| Navegador | sim | portal assistido |
| Office local | não encontrado | Graph HTTP, não automação Office |
| Automação de tela | não encontrada | portal é manual, não robotizado |
| Caminhos locais | sim, extensivos | fonte de verdade e documentos |
| SQLite | sim | apenas módulos V0.4, não emissão fiscal |
| JSON/arquivos locais | sim | persistência fiscal principal |
| Usuário logado | sim | GUI, senha do A1, confirmações, portal e Graph interativo |

## 9. Certificado e restrições operacionais

### 9.1 Tipo e localização

- foi localizado um certificado **A1 em PFX** dentro de `certificado/<emissor>/`;
- o código também aceita `.p12`;
- o caminho do certificado é salvo no perfil do emissor;
- a senha não é salva; permanece em `StringVar` e é passada ao PowerShell por variável de ambiente temporária;
- o sistema auto-localiza um único PFX na pasta do emissor;
- um perfil adicional usa portal assistido e não possui operação API equivalente no artefato.

Nenhum conteúdo, validade, serial ou chave privada foi lido. Assim, emissor, cadeia, validade e processo real de renovação permanecem decisões pendentes.

### 9.2 Operação cloud

Um A1/PFX **é tecnicamente compatível com operação não interativa**, desde que o material e sua senha sejam disponibilizados por secret manager/vault a uma identidade de workload e que as regras contratuais/fiscais o permitam. O código atual não atende a isso porque:

- exige digitação humana da senha por sessão;
- depende de PowerShell/.NET Windows;
- carrega o PFX como exportável e com `PersistKeySet`;
- exporta chave privada para PEM temporário **sem criptografia** para mTLS;
- não aplica permissões explícitas ao arquivo temporário;
- não monitora expiração, renovação ou revogação;
- o PIN local é apenas SHA-256 sem salt e não é controle de identidade/autoridade.

O uso de SHA-1 na assinatura XMLDSIG está explícito no signer. Pode ser exigência do leiaute/provedor e não deve ser trocado isoladamente; deve ser validado contra o XSD/manual vigente e coberto por golden master.

## 10. Persistência e documentos

### 10.1 Estado financeiro/fiscal

Por emissor, arquivos JSON armazenam:

- clientes;
- estado de próxima DPS por ambiente;
- programações;
- faturamentos;
- vínculo posterior com número/chave/arquivos;
- configuração e último emissor/ambiente.

`load_json` silencia qualquer exceção e retorna default. `save_json` sobrescreve diretamente o arquivo, sem arquivo temporário, `fsync`, compare-and-swap, versionamento ou lock. Corrupção ou duas gravações concorrentes podem perder estado.

### 10.2 Documentos

Foram inventariados, sem leitura de conteúdo:

| Tipo | Quantidade observada | Armazenamento |
|---|---:|---|
| JSON | 92 | configuração, dados, payloads e resultados |
| XML | 54 | DPS assinada/não assinada e NFS-e |
| PDF | 14 | DANFSe e boletos |
| SQLite | 3 | banco V0.4 e backups |
| PFX | 1 | certificado A1 |
| log | 1 | log técnico local |

Tudo está na mesma árvore do aplicativo, sob OneDrive. Nomes de emissor/tomador e números de documentos aparecem em caminhos. Não há criptografia de aplicação, bucket privado, metadados imutáveis, política de retenção, controle por função, URL temporária, WORM ou restore drill.

## 11. Determinismo

### 11.1 Cálculo

`fiscal_engine.calculate` é determinístico para o mesmo `company`, perfil e valor:

- usa `Decimal`;
- arredonda cada tributo em duas casas com `ROUND_HALF_UP`;
- mantém regras explícitas para Simples, retenções federais, ISS e limites;
- não faz I/O, rede, acesso ao relógio ou leitura global.

O teste existente cobre somente quatro combinações e passou.

### 11.2 Emissão completa

O sistema completo **não** é determinístico para a mesma entrada de negócio, porque inclui:

- `datetime.now()` em DPS e metadados;
- contador mutável de DPS;
- valores lidos diretamente de `StringVar` durante a thread;
- paths e IDs baseados em relógio;
- configuração local mutável;
- retorno do provedor;
- pós-processamento e arquivos locais.

Para ser reproduzível, o serviço futuro deve receber snapshot imutável contendo versão de regra, emissor, configuração fiscal, competência, valor, identificador lógico, número/serie DPS reservado e instante de emissão controlado.

## 12. Idempotência e como o sistema reconhece uma nota

### 12.1 Idempotência atual

Não existe chave de idempotência para emissão. Também não há tabela/unique constraint que relacione uma intenção de faturamento a uma única chamada externa.

Há controles parciais, mas insuficientes:

- geração mensal evita duplicar lançamentos por `(programacao, mês)` apenas na lista JSON em memória;
- faturamento com `nfse` preenchida não permite preparar outra emissão pela mesma tela;
- importação de PDF tenta deduplicar por chave ou número/competência;
- cada tentativa recebe um número DPS previamente incrementado;
- manifesto/hashes ajudam auditoria, não deduplicação.

### 12.2 Como sabe que já foi emitida

O sistema considera emitida quando:

- existe `resumo_emissao.json` com status local;
- faturamento recebe `nfse`/`chave` depois da callback de sucesso;
- histórico varre pastas de emissão;
- no portal, o operador registra/importa o DANFSe.

Não há verificação autoritativa automática junto à SEFIN antes de repetir.

## 13. Concorrência

### 13.1 Duas emissões simultâneas

No mesmo processo, o botão é desabilitado, reduzindo duplo clique. Isso não protege contra:

- dois processos `app.py` abertos;
- shell V0.4 abrindo múltiplos subprocessos;
- outra máquina usando a pasta sincronizada;
- corrida entre threads/gravações;
- futura integração online concorrente.

`_allocate_dps` executa read-modify-write em JSON sem lock. Duas execuções podem obter o mesmo número DPS, perder incrementos ou sobrescrever estado. As gravações de programações/faturamentos têm a mesma fragilidade.

Além disso, `_emit_worker` lê objetos Tk a partir de thread secundária, padrão não seguro para Tkinter.

### 13.2 Impacto

Risco: **crítico**, pois pode produzir DPS duplicada/conflitante, intenção duplicada, perda de vínculo ou emissão repetida após estado divergente.

## 14. Timeout, erros e reconciliação

### 14.1 Timeout após envio

O legado reconhece corretamente que `Timeout`/`ConnectionError` pode significar resultado indeterminado e grava aviso para não repetir. Porém:

- o estado é apenas arquivo/texto e mensagem ao operador;
- não há status `uncertain` consultável;
- não há bloqueio por chave de negócio;
- não há job de reconciliação;
- não há lease/retomada;
- um operador ou segundo processo ainda pode emitir novamente.

### 14.2 Provedor e reconciliação

A documentação oficial confirma:

- `GET /dps/{id}` recupera a chave de acesso pela identificação da DPS;
- `HEAD /dps/{id}` informa se houve geração;
- `GET /nfse/{chaveAcesso}` consulta a NFS-e;
- APIs ADN permitem recuperar documentos e eventos;
- `GET /nfse/{chaveAcesso}/eventos` consulta eventos.

Logo, é viável implementar reconciliação objetiva para a tentativa que já possui `id_dps`. O legado não implementa nenhuma dessas chamadas.

### 14.3 Taxonomia de erros

Atual:

- timeout/conexão → indeterminado textual;
- qualquer HTTP diferente de 201 → `RuntimeError` genérico;
- rejeições de negócio, 4xx, 429 e 5xx não formam classes/estados distintos;
- corpo de erro bruto é inserido na exceção e salvo localmente;
- não há retry automático, backoff ou circuit breaker;
- erro após HTTP 201 é corretamente tratado como autorização com pendência local.

Necessário:

- `rejected` para rejeição fiscal definitiva;
- `transient_failure` para 429/5xx/indisponibilidade antes de envio confirmado;
- `uncertain` para falha após início do POST ou resposta ambígua;
- `local_permanent_failure` para validação/assinatura/configuração;
- reconciliação antes de qualquer retry de efeito externo.

## 15. Cancelamento e substituição

O código não contém comando de cancelamento ou substituição. O histórico apenas marca uma nota como cancelada se encontrar arquivo com nome esperado, presumivelmente inserido por processo externo/manual.

O provedor oferece API genérica de eventos (`POST /nfse/{chaveAcesso}/eventos`) e consulta de eventos; a documentação também descreve substituição por DPS referenciando a chave da NFS-e substituída. Essas capacidades precisam de implementação futura, autorização forte, idempotência própria e golden master. Não foram testadas nesta etapa.

## 16. Múltiplos emissores e segregação

O legado modela múltiplos emissores por perfil e separa:

- empresa/configuração fiscal;
- pasta de certificado;
- clientes, programações, faturamentos e numeração;
- diretório de emissão e ambiente;
- método API A1 ou portal assistido.

A segregação é apenas lógica/de diretório. Todos rodam sob o mesmo usuário Windows, processo, instalação e permissões de filesystem. Um operador com acesso ao aplicativo pode editar perfis fiscais, endpoints, CNPJ, certificado e próxima DPS. Não há IAM por estabelecimento, aprovação, trilha append-only ou processo separado por certificado.

## 17. Regras fiscais e retenções

### 17.1 Regras identificadas

- perfis: profissional, sem retenções federais e perfil da empresa;
- regimes: Lucro Presumido, Lucro Real e Simples Nacional;
- ISS, PIS, COFINS, CSLL e IRRF configuráveis por emissor;
- PCC calculado como soma arredondada de PIS + COFINS + CSLL;
- retenção social somente quando o total calculado é maior que o limite configurado;
- IRRF somente quando maior que o limite;
- ISS retido apenas por configuração explícita;
- no Simples, IRRF/PCC são zerados e o grupo federal é omitido; ISS não retido é zerado no cálculo local;
- líquido = bruto − retenções efetivas.

### 17.2 Pontos fiscais que exigem validação especializada

Não foi feita validação jurídico-tributária. Antes de refatorar, contador/responsável fiscal deve confirmar:

- limites e regra estrita `>` versus `>=`;
- arredondamento por tributo e arredondamento do agregado;
- exceções de Simples/Anexo IV, órgãos públicos, INSS e ISS municipal;
- vigência/versão da regra por competência;
- origem e atualização de alíquotas e percentuais aproximados;
- mapeamento XML de `vRetCSLL`: o código preenche o campo com o agregado social, não apenas `csll`; isso deve ser confrontado com leiaute vigente e XMLs sintéticos/golden masters, sem “corrigir” por suposição;
- ausência do XSD declarado na validação: `VALIDACAO_V031.txt` diz ter usado DPS v1.01, mas nenhum `.xsd` foi localizado no pacote.

## 18. Logs e observabilidade

### 18.1 Estado atual

- log único `data/app.log`;
- mensagens incluem ambiente, ID do emissor, DPS, NFS-e e nome de cliente;
- exceções completas são registradas;
- resposta HTTP integral, payload integral e JSON do provedor são salvos em disco;
- falhas de importação podem gerar arquivo com nome de origem e mensagem;
- não há rotação, retenção, redação, correlação, métricas, traces ou alertas;
- não há auditoria append-only de quem aprovou/emitiu/alterou configuração.

### 18.2 Lacunas contra a arquitetura aprovada

O desenho aprovado exige logs por allowlist/redação, correlação ponta a ponta, métricas de `uncertain`, divergências, expiração do certificado, auditoria oficial no STK OS e documentos em storage privado. O legado não satisfaz esses controles.

## 19. Secret scan e segurança

### 19.1 Resultado do scan

Escopo textual seguro: fontes `.py`, scripts `.ps1/.bat`, documentação operacional e `config.json`, sem varrer conteúdo de documentos/dados de clientes.

- nenhum marcador de chave privada PEM foi encontrado no texto;
- nenhum padrão AWS/JWT/URL com credencial foi encontrado;
- referências a senha/token aparecem em código de passagem/variáveis, não como valor revelado;
- um arquivo A1/PFX real foi inventariado por metadado;
- configuração contém endpoints e flag de produção, sem chaves de segredo detectadas;
- dados identificáveis e contatos reais estão hardcoded no default de `app.py` e em caminhos/arquivos de dados;
- não existe `.env` do legado, mas isso não significa ausência de secrets: o PFX é o principal segredo material.

### 19.2 Achados priorizados

| Prioridade | Achado | Evidência/impacto |
|---|---|---|
| P0 | A1/PFX na árvore do aplicativo/OneDrive | exfiltração da identidade fiscal e blast radius alto |
| P0 | Sem idempotência/lock na emissão e DPS | duplicidade ou conflito sob concorrência/retry |
| P0 | Estado incerto sem reconciliação automática | timeout pode virar reemissão indevida |
| P1 | Chave exportável, `PersistKeySet` e PEM temporário sem senha | aumenta exposição da chave no host |
| P1 | Documentos/payloads/respostas reais em filesystem local | PII/fiscal sem storage privado/controle/retention |
| P1 | Resposta HTTP integral e erros brutos persistidos | vazamento em logs/arquivos e retenção indefinida |
| P1 | JSON não atômico e sem transações | perda/corrupção de estado e divergência fiscal |
| P1 | Sem cancelamento, substituição ou consulta | operação incompleta e recuperação manual |
| P1 | Dependências sem lock e versão Python não declarada | build irreproduzível; CVEs exatos não auditáveis |
| P1 | Runtime desktop, senha/portal/Graph interativos | incompatível com operação 24/7 |
| P1 | Configuração fiscal/endpoints/produção editáveis localmente | sem RBAC, aprovação ou trilha confiável |
| P2 | PIN local SHA-256 sem salt | não é autenticação adequada e é atacável offline |
| P2 | Sem validação de expiração/cadeia/uso do A1 antes da fila | falha operacional previsível |
| P2 | Endpoint configurável sem allowlist | alteração local pode desviar payload/mTLS |
| P2 | Logs sem rotação/redação/correlação | exposição e baixa capacidade de incidente |
| P2 | Fontes Windows e paths com nomes de clientes | metadados sensíveis e portabilidade reduzida |
| P2 | Parsing XML/PDF sem limites de tamanho explícitos | risco de consumo de recursos em arquivos malformados |

### 19.3 Bibliotecas vulneráveis/obsoletas

Não é tecnicamente correto atribuir CVEs a ranges. Como não há `pip freeze`, lockfile ou ambiente do legado preservado, a versão efetiva de cada biblioteca é desconhecida. O achado acionável é **supply chain não reproduzível**. No início da implementação futura, a baseline sanitizada deve gerar lock com hashes, SBOM e scan OSV/pip-audit; isso não foi feito aqui para não instalar nem alterar o legado.

## 20. Testabilidade atual

Existem três scripts ad hoc, sem framework:

| Teste | Cobertura | Resultado nesta inspeção |
|---|---|---|
| `test_fiscal_engine.py` | 3 valores no Lucro Presumido + 1 Simples | passou em Python 3.12.13 |
| `test_cnpj_lookup.py` | normalização com sessão fake | não executado por dependência ausente |
| `test_address_xml.py` | estrutura parcial do endereço | não executado por import com side effect |

Não há testes de:

- XML DPS completo/XSD no pacote;
- assinatura XMLDSIG;
- certificado errado/expirado;
- HTTP 201, rejeições, 429, 5xx e corpos inválidos;
- timeout antes/depois do aceite;
- idempotência e concorrência;
- consulta/reconciliação;
- cancelamento/substituição;
- persistência/crash entre autorização e atualização do faturamento;
- múltiplos emissores;
- golden PDF/DANFSe;
- migração entre versões.

## 21. Percentual e áreas reaproveitáveis

### 21.1 Estimativa

O repositório tem aproximadamente 6,9 mil linhas de Python/PowerShell relevante, das quais `app.py` contém 3.772 linhas. Considerando apenas o caminho fiscal (cálculo, DPS, assinatura, transporte, retorno, PDF/importação):

- **45–55% já está em código sem dependência direta de Tkinter**, sobretudo cálculo, DANFSe, PDF import e signer;
- **70–80% do comportamento fiscal validado é reaproveitável** após extrair código atualmente embutido em `app.py`;
- **20–30% deve ser substituído**, não preservado: GUI, JSON local, browser/clipboard, Graph delegado, mutações de `StringVar`, controles manuais, armazenamento local e coordenação sem lock.

São estimativas por responsabilidade/LOC, não medida de cobertura.

### 21.2 Reuso por componente

| Componente | Reuso estimado | Tratamento |
|---|---:|---|
| `fiscal_engine.py` | 90–100% | congelar e caracterizar antes de qualquer mudança |
| montagem XML DPS | 70–85% | extrair preservando ordem/mapeamentos; injetar snapshot/clock/DPS |
| `danfse.py` | 80–90% | parametrizar fontes/assets; golden visual |
| `danfse_pdf_import.py` | 70–85% | manter apenas se portal continuar; limitar arquivos |
| resposta SEFIN/decompressão | 70–85% | extrair e tipar estados/erros |
| `signer.ps1` | 30–60% | preservar comportamento como oracle; substituir manejo de chave |
| `requests` provider client | 40–60% | sessão dedicada, taxonomia, telemetry, egress e reconciliação |
| programações/faturamentos | 20–40% como código | modelo deve migrar para STK OS/PostgreSQL; regras podem orientar |
| Graph/e-mail | 0% no motor fiscal | mover para integração de entrega do STK OS |
| GUI Tkinter | 0% no serviço | manter apenas como legado/oracle temporário |

## 22. Golden master proposto

### 22.1 Princípios

- usar somente emissores, CNPJs, clientes, chaves, XMLs e PDFs sintéticos;
- fixar versão de regra, clock, timezone, série e número DPS;
- comparar valores exatos como `Decimal`/strings, nunca float;
- canonicalizar XML para comparação sem depender de formatação;
- usar certificado A1 de teste/homologação, nunca o real;
- separar golden de cálculo, payload, assinatura, transporte, resposta e documento;
- armazenar hashes e revisão do responsável fiscal.

### 22.2 Matriz mínima

| Grupo | Casos sintéticos |
|---|---|
| Entrada | campos mínimos, endereço completo/incompleto, CNPJ numérico/alfanumérico válido em forma, caracteres especiais, limites de tamanho |
| Cálculo | valores já testados; centavos `.005`; zero/negativo; cada perfil; Lucro Presumido/Real/Simples |
| Retenções | abaixo, exatamente e acima de R$ 10; ISS retido/não retido; PCC/IRRF aplicável e não aplicável |
| Payload | XML completo por regime, ausência/presença de `tribFed`, endereço, pedido, totais aproximados, `vRetCSLL` validado |
| Assinatura | canonicalização, referência `Id`, certificado de teste correto/incorreto, verificação da assinatura |
| Sucesso | HTTP 201 válido, ambiente correto/incorreto, XML ausente, base64/gzip inválido |
| Rejeição | 400/422 com uma e múltiplas regras, corpo não JSON, mensagem sanitizada |
| Transitório | 429, 500, 502, 503, falha TLS/DNS antes de transmitir |
| Timeout | connect timeout; read timeout após envio; reconciliação HEAD/GET encontra/não encontra DPS |
| Idempotência | mesma chave repetida antes, durante e após sucesso; payload divergente com mesma chave deve falhar |
| Concorrência | 2, 10 e 50 solicitações da mesma competência; única chamada externa e DPS única |
| Crash | queda após reservar DPS, após persistir intenção, após POST, após 201 e antes do upload/commit |
| Cancelamento | aceite, rejeição, timeout e repetição do mesmo evento |
| Substituição | nova DPS referencia nota original; original `superseded`, nova `issued`, repetição idempotente |
| PDF/XML | hash semântico, campos visuais e renderização em Linux/Windows; nomes sem PII |
| Multiemissor | certificado/configuração corretos por estabelecimento; tentativa cruzada bloqueada |

### 22.3 Ordem de captura

1. congelar hashes desta baseline;
2. criar fixtures sintéticas aprovadas fiscalmente;
3. capturar saída do `fiscal_engine` sem alterar código;
4. criar harness que reproduza `_build_unsigned_dps` com relógio/DPS injetados;
5. validar contra XSD oficial versionado;
6. assinar somente com A1 de teste e comparar assinatura semanticamente;
7. simular transporte com fake server sem egress;
8. obter goldens em produção restrita apenas em etapa autorizada posterior;
9. exigir dupla execução comparativa antes do corte.

## 23. Comparação A/B/C/D baseada no código

| Critério | A — wrapper | B — serviço privado | C — worker modular | D — reescrita |
|---|---|---|---|---|
| Reuso de regra | 90%+ | 70–80% comportamento | 70–80% comportamento | baixo no início |
| Mudança inicial | menor | média | média | maior |
| Retirada da GUI | não necessariamente | sim | sim | sim |
| Windows | herdado | pode ser isolado/retirado | conflita com runtime do backend | definível |
| Certificado | herdado e frágil | **isolamento próprio** | acesso no worker compartilhado, salvo workload separado | definível |
| Idempotência | externa e parcial | **fronteira + núcleo** | PostgreSQL/worker facilita | precisa reconstruir |
| Reconciliação | adaptador adicional | responsabilidade explícita | responsabilidade do módulo | nova implementação |
| Blast radius | VM/processo legado | **fiscal isolado** | maior sobre worker/deploy | configurável |
| Testabilidade | baixa | alta após extração | alta após extração | alta, mas exige revalidação total |
| Infra | Windows/GUI onerosa | um workload privado adicional | menor número de workloads | alta durante transição |
| Operação 24/7 | ruim no portal/senha | boa após vault/API | boa após isolamento adequado | futura |
| Risco fiscal | médio/alto | **menor equilíbrio** | médio | alto |
| Manutenção | dívida preservada | fronteira clara | dependências fiscais no monorepo/runtime | base nova, validação cara |

### 23.1 A — wrapper temporário

Não é recomendação-alvo. `_emit_worker` não é uma unidade headless: lê `StringVar`, agenda callbacks Tk, grava arquivos e chama PowerShell. Hospedar isso exigiria Windows, sessão/GUI ou emulação frágil. Poderia existir apenas como contingência curta para o emissor de portal, com operador humano e prazo de retirada, nunca como arquitetura 100% online.

### 23.2 B — extração para serviço privado

É a melhor relação risco/transformação:

- preserva o cálculo e mapeamentos validados;
- permite runtime Python/OS independente do FastAPI atual;
- isola A1, bibliotecas nativas, PowerShell temporário e egress fiscal;
- reduz blast radius de falha, vazamento ou dependência do provedor;
- torna máquina de estados, idempotência e reconciliação responsabilidades explícitas;
- não exige uma arquitetura ampla de microserviços: é um único limite fiscal justificado pelo segredo e efeito externo crítico.

### 23.3 C — incorporação ao worker/backend modular

C é tecnicamente possível depois que o núcleo virar biblioteca portátil. Porém, neste artefato:

- runtime observado é CPython 3.14, enquanto o backend aceita 3.12–3.13;
- assinatura depende de Windows/PowerShell;
- dependências de PDF/XML/crypto ampliam a imagem e a cadeia de supply chain do backend;
- certificado e egress ficariam próximos do worker geral;
- falha fiscal pode afetar deploy/recursos do worker do STK OS.

Se, após golden masters, a assinatura for portada e o processo fiscal puder ser um workload separado com IAM, secret e egress próprios, C pode aproximar-se de B operacionalmente. Nesse caso ele já estaria, na prática, implantado como um worker fiscal isolado. Para a V1 inspecionada, B torna essa fronteira inequívoca e mais segura.

### 23.4 D — reescrita controlada

Não há evidência para reescrever regras fiscais. O núcleo puro existe, o fluxo produziu resultados operacionais e as lacunas estão principalmente em fronteira, estado, segurança e operação. Reescrever aumentaria o risco de regressão e a carga de validação.

## 24. Arquitetura recomendada

```text
STK OS / PostgreSQL
  ├─ contrato, competência, snapshot, autorização e idempotência de negócio
  └─ outbox → worker STK OS
                 └─ API privada autenticada
                      → Serviço Fiscal Python
                           ├─ máquina de estados + idempotência durável
                           ├─ núcleo fiscal preservado
                           ├─ builder/validator DPS versionado
                           ├─ signer com A1 via vault/workload
                           ├─ client SEFIN + reconciliação
                           └─ upload autenticado → storage privado

SEFIN/ADN ← TLS/mTLS + egress allowlist → Serviço Fiscal
Graph/e-mail ← outbox de entrega do STK OS, fora do motor fiscal
```

O STK OS é dono da intenção financeira. O serviço fiscal é dono da execução técnica fiscal e de seu estado até resultado inequívoco. PDF/XML ficam em storage privado com hash e metadados no STK OS. O n8n não participa do caminho crítico.

## 25. Mudanças mínimas necessárias

1. Criar baseline sanitizada em Git com os hashes desta versão; remover dados/certificado da cópia de desenvolvimento.
2. Congelar `fiscal_engine.py`, builder XML, parser de retorno e DANFSe sob golden masters.
3. Extrair um caso de uso headless que receba snapshot imutável; nenhuma dependência de Tkinter.
4. Reservar DPS e intenção em transação durável antes da chamada externa.
5. Introduzir chave de idempotência, unique constraints, lease e estados explícitos.
6. Implementar reconciliação por `/dps/{id}`, `/nfse/{chave}` e eventos.
7. Criar taxonomia de erros; retry apenas para fases seguras e sempre com reconciliação.
8. Mover PFX/senha para vault/secret manager; eliminar PFX no diretório e PEM persistente/temporário inseguro.
9. Decidir se o signer inicial fica em runtime Windows isolado ou é portado sob golden master para biblioteca homologada.
10. Mover documentos para storage privado; persistir hashes, classificação, retenção e vínculo.
11. Remover Graph, navegador, clipboard e portal do serviço fiscal.
12. Adicionar autenticação M2M, egress allowlist, logs redigidos, métricas e traces.
13. Fixar Python/dependências com lock, hashes, SBOM e scans.
14. Implementar cancelamento/substituição como comandos separados e autorizados.

## 26. Riscos da migração

| Risco | Mitigação exigida |
|---|---|
| alterar centavos/retenções | golden master e aprovação fiscal |
| mudar XML/ordem/canonicalização | XSD oficial + assinatura/fixture comparativa |
| colisão de DPS no corte | dono único da sequência, janela de freeze e reconciliação |
| nota aceita e migração não registrar | estado `uncertain`, consulta por DPS e backfill |
| certificado errado | vínculo rígido estabelecimento→secret/key ID e validação |
| divergência Python 3.14 vs 3.12 | runtime próprio B e matriz de testes |
| diferença de fontes/PDF | golden render e fonte empacotada/licenciada |
| importar dados locais inconsistentes | migração auditada, hashes e relatório de divergência |
| portal-only não automatizável | obter A1/API ou manter fila humana explicitamente |
| coexistência legado/novo emitir duplicado | kill switch, single writer e cutover por emissor |

## 27. Ordem recomendada de implementação

Esta ordem é recomendação para etapa posterior; **não foi iniciada**:

1. contenção e baseline sanitizada;
2. decisão fiscal/contábil sobre fixtures e pontos ambíguos;
3. golden masters de cálculo/XML/assinatura/retorno;
4. modelo persistente de intenção, estados e idempotência;
5. extração headless sem transporte real;
6. client de reconciliação e fake provider;
7. certificado de teste em vault e signer isolado;
8. emissão somente em produção restrita;
9. storage/documentos/observabilidade;
10. cancelamento e substituição em produção restrita;
11. dupla execução comparativa sem duplicar efeito;
12. cutover controlado por emissor, com legado bloqueado para escrita;
13. período de reconciliação intensiva e retirada do wrapper/desktop.

## 28. Pontos que exigem decisão do negócio

1. Qual perfil/emissor é prioridade para migração?
2. Todos os emissores obterão A1/API? O emissor hoje via portal pode permanecer humano temporariamente?
3. Quem é responsável por aprovar regras, limites, exceções e goldens fiscais?
4. Qual sistema será dono da sequência DPS durante coexistência/cutover?
5. Quais papéis podem emitir, cancelar, substituir, reconciliar e liberar caso incerto?
6. Qual política de dupla aprovação existe para cancelamento/substituição e alterações fiscais?
7. Qual SLO, janela fiscal, RPO/RTO e plantão são necessários?
8. Qual retenção de XML/PDF/payload/log e base legal/LGPD será aprovada?
9. Qual provedor de cloud/vault/storage será usado e em qual região?
10. Aceita-se runtime Windows privado temporário para preservar o signer, ou a portabilidade Linux é requisito imediato?
11. Como será renovado/revogado o A1 e quem terá custódia?
12. O envio por e-mail continuará delegado a usuário ou migrará para identidade app-only?

## 29. Critérios de saída antes de qualquer integração

- baseline sanitizada e versionada;
- nenhuma chave/certificado/dado real no repositório;
- fixtures sintéticas aprovadas;
- regra fiscal e XML cobertos por golden master;
- idempotência e concorrência comprovadas;
- timeout reconciliado por DPS sem reemissão cega;
- cancelamento/substituição testados em produção restrita;
- certificado de teste isolado em vault;
- documentos em storage privado;
- logs redigidos e auditoria oficial no STK OS;
- decisão formal para o emissor que hoje depende de portal;
- plano de single-writer/cutover aprovado.

## 30. Decisão final

**ARQUITETURA FISCAL RECOMENDADA: B**

A alternativa B venceu porque o núcleo de cálculo e parte relevante do comportamento fiscal são preserváveis, tornando D desnecessária, mas o fluxo atual ainda depende de Tkinter, Windows/PowerShell, certificado local, arquivos sem transação e execução humana. Essas dependências, somadas ao risco de duplicidade e à necessidade de isolar A1, egress e falhas do provedor, justificam um único serviço fiscal privado. C só alcançaria segurança equivalente se o worker fiscal recebesse runtime, processo, IAM, certificado e egress próprios — isto é, uma fronteira operacional próxima da própria B.

Nenhuma solução foi implementada e a Etapa 4 não foi iniciada.
