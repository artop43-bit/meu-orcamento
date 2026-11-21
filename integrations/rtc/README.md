# Motores da Reforma Tributária

Em **Meu Orçamento → Análises → Ferramentas → Reforma Tributária**, a API consulta os motores oficiais executados no mesmo ambiente. A data da operação determina a vigência dos dados fiscais.

| Ferramenta | Fonte | Revisão da imagem |
|---|---|---|
| Regime Regular e tabelas oficiais | [Receita Federal · Regime Regular](https://github.com/ReceitaFederal/calculadora-rtc-regime-regular) | `f1eebd7ce3157423b1a6aaca7dc1d6c3395452c4` |
| Simples Nacional | [Receita Federal · Simples Nacional](https://github.com/ReceitaFederal/calculadora-rtc-simples-nacional) | `a926d5a76095ac0295a6612a9a54db7ffead2396` |
| DANFSe | [Receita Federal · gerador de DANFSe](https://github.com/ReceitaFederal/calculadora-rtc-gerador-danfse) | `8d79e6b2f7fad6375340afcb51c85ed370c64a14` |

As imagens incluem as licenças MIT dos repositórios. A construção baixa os códigos e suas dependências e cria a base fiscal a partir das migrações Flyway do Regime Regular. Os dois motores Java usam essa cópia somente para leitura. Em execução, os motores ficam na rede interna `rtc`, sem portas publicadas, e o backend é o único serviço do aplicativo ligado a ela. A atualização dos códigos e da base é feita ao revisar e reconstruir as imagens.

- **Regime Regular.** A base empacotada tem alíquotas de referência para 2026. Para 2027 em diante, informe as alíquotas do cenário. Resultados parciais somam os itens que o motor calculou.
- **Simples Nacional.** O formulário recebe as alíquotas efetivas. Para NFS-e, o fluxo atende ME/EPP com IBS e CBS no Simples, com um item de serviço e dados de ISS. O valor de IS eventualmente informado em NF-e/NFC-e é exibido como recebido.
- **DANFSe.** A ferramenta gera uma representação em PDF de um XML de NFS-e do padrão nacional, de até 5 MB. O Meu Orçamento não guarda o XML nem o PDF. A emissão da nota ocorre no sistema emissor.

Para testar o contrato com os motores de uma stack local já iniciada, rode da raiz do projeto em um shell Bash:

```sh
docker compose exec -T backend python - < integrations/rtc/smoke.py regular simples
docker compose exec -T backend python -c 'from app.services.rtc import gerar_danfse; import sys; assert gerar_danfse(sys.stdin.buffer.read()).startswith(b"%PDF-")' < integrations/rtc/nfse-teste.xml
```

O CI executa `smoke.py` com os três motores ARM64 sem acesso externo. O teste de navegador `e2e/rtc.py` pode usar os motores reais definindo `QA_RTC_REAL=1` e apontando para um ambiente de teste com os três serviços ativos.
