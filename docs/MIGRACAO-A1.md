# Migração para a VM gratuita (A1.Flex)

A VM atual (`meu-orcamento`, shape **VM.Standard.A2.Flex**, 0,5 OCPU e 6 GB) não está entre as
máquinas **Always Free** da Oracle e roda com os créditos do teste grátis, que terminam por volta
de **15/11/2026**. Depois disso, a Oracle para (e depois apaga) recursos que não são gratuitos.
A **VM.Standard.A1.Flex** (Ampere) é gratuita para sempre (até 4 OCPUs e 24 GB no total).

O endereço do site não muda: o **IP reservado 144.22.130.13** passa da VM antiga para a nova.
O site fica fora do ar só durante a troca (poucos minutos).

Quem faz o quê: os passos 🖱️ são no **console da Oracle** (você); os passos 💻 são no PC, com o
script `deploy/scripts/migrate-host.sh` (eu rodo).

---

## 1. 🖱️ Criar a VM nova (cerca de 5 minutos)

Console da Oracle → **Compute → Instances → Create instance**:

| Campo | Valor |
|---|---|
| **Name** | `meu-orcamento-a1` |
| **Compartment** | o mesmo da VM atual |
| **Placement** | `AD-1` (o mesmo da atual: SA-SAOPAULO-1-AD-1) |
| **Image** | *Change image* → **Canonical Ubuntu 24.04** |
| **Shape** | *Change shape* → **Ampere** → **VM.Standard.A1.Flex** → **2 OCPUs** e **12 GB** de memória. Confira o selo **"Always Free-eligible"** |
| **Primary VNIC** | *Select existing virtual cloud network*: **vcn-20261016-2044**; subnet: a **pública** (10.0.0.0/24) |
| **Public IPv4 address** | **Assign a public IPv4 address** (temporário; o IP reservado vem no passo 4) |
| **SSH keys** | **Paste public keys** → cole o conteúdo do arquivo `C:\ArthurClaude\meu-orcamento-chave-publica-ssh.txt` (é a parte **pública** da chave que já usamos; não é segredo) |
| **Boot volume** | padrão (50 GB) |

Clique em **Create**. Quando ficar **Running**, anote o **IP público** e me envie.

Se aparecer **"Out of capacity"**: tente **1 OCPU e 6 GB** (dá para aumentar depois, sem custo,
até 4 OCPUs e 24 GB) ou tente de novo mais tarde. É comum em São Paulo.

## 2. 💻 Preparar a VM nova (o site continua no ar)

```bash
deploy/scripts/migrate-host.sh preparar 144.22.130.13 <IP_NOVO>
```

Instala Docker, firewall, SSH endurecido e fail2ban; copia a chave de leitura do GitHub, o
`.env.production` e o certificado HTTPS **de uma VM para a outra, sem passar pela tela**; clona o
repositório e constrói as imagens.

## 3. 💻 Trocar (janela de manutenção de poucos minutos)

```bash
deploy/scripts/migrate-host.sh trocar 144.22.130.13 <IP_NOVO>
```

Para o app na VM antiga (o banco fica ligado), copia o banco e os backups para a nova, **confere as
contagens** das tabelas principais e sobe tudo na nova. Se algo não bater, nada é trocado e
`deploy/scripts/migrate-host.sh voltar 144.22.130.13 <IP_NOVO>` religa a antiga.

## 4. 🖱️ Mover o IP reservado (cerca de 2 minutos)

1. **VM antiga** (`meu-orcamento`) → **Attached VNICs** → VNIC → **IPv4 Addresses** → ⋯ →
   **Edit** → *Public IP type*: **No public IP** → **Update** (libera o 144.22.130.13).
2. **VM nova** (`meu-orcamento-a1`) → **Attached VNICs** → VNIC → **IPv4 Addresses** → ⋯ →
   **Edit** → *Public IP type*: **Reserved public IP** → escolha **144.22.130.13** → **Update**.

## 5. 💻 Concluir

```bash
deploy/scripts/migrate-host.sh concluir 144.22.130.13 <IP_NOVO>
```

Confere o site pelo endereço público e o acesso SSH na VM nova.

## 6. 🖱️ Depois de alguns dias

- Deixe a VM antiga **parada** (*Stop*, não *Terminate*) por uns 7 dias, como garantia.
- Depois, **Terminate** a VM antiga marcando **"Permanently delete the attached boot volume"**.
- Quando o GitHub voltar: atualizar o segredo `DEPLOY_KNOWN_HOSTS` com a chave da VM nova
  (eu faço com `ssh-keyscan` + `gh secret set`).

## Ensaio (a qualquer hora, sem parar o site)

```bash
deploy/scripts/migrate-host.sh ensaiar 144.22.130.13 -
```

Copia o banco de produção para um PostgreSQL descartável pelo mesmo caminho da troca e compara as
contagens. Ensaiado em 21/10/2026: todas as tabelas bateram.
