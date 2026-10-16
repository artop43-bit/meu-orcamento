# Deploy na Oracle Cloud

Guia para colocar o Meu Orçamento no ar numa VM gratuita (Always Free) da Oracle, com
domínio próprio, HTTPS automático, backup diário criptografado e deploy automático a cada
merge na `main`.

```
Internet ──► Caddy (80/443, HTTPS) ──► /api/* ──► API (FastAPI) ──► PostgreSQL
                    └──────────────► frontend (arquivos estáticos)
             scheduler: limpeza diária     backup: pg_dump → age → Object Storage
```

Tempo estimado: 1h30 na primeira vez. Os passos marcados com 🔐 envolvem chaves e senhas:
**faça você mesmo e não compartilhe esses valores com ninguém** (nem em chats).

---

## 0. Antes de começar

Você vai precisar de:

- Conta na Oracle Cloud (pede cartão só para verificação; o plano Always Free não cobra).
- Um domínio (ex.: registro.br, ~R$ 40/ano).
- Conta num serviço de e-mail transacional (ex.: Brevo, 300 e-mails/dia grátis).
- No seu PC (Windows), o `age` para gerar a chave dos backups:
  ```powershell
  winget install --id FiloSottile.age -e
  ```

---

## 1. Criar a VM

1. Console da Oracle → **Compute → Instances → Create instance**.
2. **Image:** Canonical Ubuntu 24.04. **Shape:** Ampere `VM.Standard.A1.Flex`
   (ex.: 2 OCPUs e 12 GB; o Always Free permite até 4 OCPUs e 24 GB no total).
   Se aparecer "Out of capacity", tente outro *Availability Domain* ou mais tarde.
3. **Networking:** deixe criar uma VCN nova com subnet pública e marque "Assign a public IPv4 address".
4. 🔐 **SSH keys:** "Generate a key pair for me" e **baixe a chave privada**. Guarde-a num lugar seguro
   (ex.: `C:\Users\<você>\.ssh\oracle-meu-orcamento.key`). Sem ela você perde o acesso à VM.
5. Crie a instância e anote o **IP público**.
6. Opcional, mas recomendado: em **Networking → Reserved Public IPs**, reserve esse IP para ele não mudar.

## 2. Abrir as portas 80 e 443 na rede da Oracle

**Networking → Virtual Cloud Networks →** sua VCN **→ Security Lists → Default Security List →
Add Ingress Rules**, uma regra para cada linha:

| Source CIDR | IP Protocol | Destination Port |
|---|---|---|
| 0.0.0.0/0 | TCP | 80 |
| 0.0.0.0/0 | TCP | 443 |
| 0.0.0.0/0 | UDP | 443 |

A porta 22 (SSH) já vem liberada. O banco de dados **não** precisa de porta aberta.

## 3. Apontar o domínio

No painel do seu domínio (ex.: registro.br → DNS), crie:

| Tipo | Nome | Valor |
|---|---|---|
| A | (vazio / @) | IP público da VM |
| A | www | IP público da VM |

A propagação leva de minutos a algumas horas. Confira com `nslookup seudominio.com.br`.

## 4. Preparar o servidor

No seu PC:

```powershell
ssh -i C:\Users\<você>\.ssh\oracle-meu-orcamento.key ubuntu@IP_DA_VM
```

O script de preparação instala o Docker, libera 80/443 no firewall da VM, desliga o login
por senha e ativa fail2ban e atualizações automáticas. Copie-o do seu PC para a VM
(na pasta do projeto):

```powershell
scp -i C:\Users\<você>\.ssh\oracle-meu-orcamento.key deploy\scripts\setup-server.sh ubuntu@IP_DA_VM:~
```

Na VM:

```bash
bash setup-server.sh
exit   # saia e entre de novo para o grupo docker valer
```

## 5. 🔐 Dar à VM acesso de leitura ao repositório

Na VM:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/github_deploy -N "" -C "meu-orcamento-servidor"
cat ~/.ssh/github_deploy.pub
cat >> ~/.ssh/config <<'EOF'
Host github.com
  IdentityFile ~/.ssh/github_deploy
  IdentitiesOnly yes
EOF
```

No GitHub: repositório → **Settings → Deploy keys → Add deploy key**, cole a chave pública
e **deixe "Allow write access" desmarcado** (só leitura).

Depois, na VM:

```bash
git clone git@github.com:artop43-bit/meu-orcamento.git ~/meu-orcamento
```

## 6. 🔐 Chave dos backups (no seu PC, não na VM)

```powershell
age-keygen -o age-key.txt
```

- A linha `# public key: age1...` é a chave **pública**: ela vai no `.env.production` (passo 8).
- O arquivo `age-key.txt` é a chave **privada**: guarde-a **fora do servidor** (gerenciador de
  senhas, pen drive). **Sem ela nenhum backup pode ser restaurado.** Com ela, quem tiver
  os arquivos de backup consegue ler seus dados, então não a envie para ninguém.

## 7. 🔐 Bucket para os backups (Object Storage)

1. **Storage → Buckets → Create Bucket:** nome `meu-orcamento-backups`, visibilidade **Private**.
2. Anote o **Namespace** (aparece em *Bucket Details*).
3. Seu perfil (canto superior direito) → **Customer Secret Keys → Generate Secret Key**.
   Copie o **Access Key** e o **Secret** (o secret só aparece uma vez).
4. O endpoint fica: `https://<namespace>.compat.objectstorage.sa-saopaulo-1.oraclecloud.com`
   (troque a região se sua VM não estiver em São Paulo).

## 8. 🔐 E-mail transacional

Exemplo com Brevo: **Senders, Domains → Domains → Add a domain**, crie no DNS os registros
que ele mostrar (SPF, DKIM e DMARC) e espere a verificação. Em **SMTP & API → SMTP**, gere
uma chave SMTP. Host `smtp-relay.brevo.com`, porta 587.

## 9. 🔐 Configurar o `.env.production`

Na VM:

```bash
cd ~/meu-orcamento
cp .env.production.example .env.production
chmod 600 .env.production
nano .env.production
```

Preencha tudo. Para gerar a senha do banco e a SECRET_KEY:

```bash
openssl rand -base64 32 | tr -d '/+=' | cut -c1-32   # POSTGRES_PASSWORD
openssl rand -base64 64 | tr -d '\n'; echo           # SECRET_KEY
```

> Guarde uma cópia do `.env.production` no seu gerenciador de senhas. A `SECRET_KEY` também
> protege os segredos de 2FA: se ela se perder, todos os usuários precisam reativar o 2FA.

## 10. Primeiro deploy

```bash
cd ~/meu-orcamento
bash deploy/scripts/deploy.sh
```

A primeira vez demora alguns minutos (compila o frontend e as imagens). Depois:

```bash
deploy/scripts/compose.sh ps            # todos devem estar "running"/"healthy"
deploy/scripts/compose.sh logs -f caddy # deve mostrar o certificado obtido
```

Abra `https://seudominio.com.br`, crie sua conta e confira se o e-mail de confirmação chegou.

Teste o backup na hora (sem esperar a madrugada):

```bash
deploy/scripts/compose.sh exec backup sh -c '. /etc/backup.env && backup.sh'
```

Deve aparecer "enviado para o bucket". Confira o arquivo no console da Oracle.

## 11. 🔐 Deploy automático pelo GitHub

A ideia: o GitHub ganha uma chave SSH que **só consegue rodar o script de deploy** no servidor.

Na VM:

```bash
ssh-keygen -t ed25519 -f ~/gh-actions -N "" -C "github-actions-deploy"
echo "command=\"bash $HOME/meu-orcamento/deploy/scripts/deploy.sh\",restrict $(cat ~/gh-actions.pub)" >> ~/.ssh/authorized_keys
cat ~/gh-actions            # chave PRIVADA: vai para o GitHub (abaixo) e depois apague
ssh-keyscan -t ed25519 localhost 2>/dev/null | sed "s/^localhost/IP_DA_VM/"   # known_hosts
```

No GitHub: **Settings → Environments → New environment** `production`. Dentro dele, em **Environment secrets**:

| Secret | Valor |
|---|---|
| `DEPLOY_SSH_KEY` | conteúdo de `~/gh-actions` (a privada) |
| `DEPLOY_KNOWN_HOSTS` | a linha gerada pelo `ssh-keyscan` (com o IP no lugar de localhost) |
| `DEPLOY_HOST` | IP público da VM |
| `DEPLOY_USER` | `ubuntu` |

E em **Settings → Secrets and variables → Actions → Variables**:

| Variável | Valor |
|---|---|
| `DOMAIN` | `seudominio.com.br` |
| `DEPLOY_ENABLED` | `true` |

Depois, na VM: `rm ~/gh-actions ~/gh-actions.pub`.

A partir daí, todo merge na `main` roda o CI e, se ele passar, o workflow **Deploy** atualiza
o servidor e confere se o site respondeu. Também dá para rodar à mão em **Actions → Deploy →
Run workflow**.

---

## Operação do dia a dia

```bash
cd ~/meu-orcamento
deploy/scripts/compose.sh ps                 # estado dos serviços
deploy/scripts/compose.sh logs -f api        # logs da API
deploy/scripts/compose.sh restart api        # reiniciar a API
deploy/scripts/compose.sh exec db psql -U orcamento orcamento   # console do banco
```

### Restaurar um backup

1. Baixe o arquivo `.dump.age` do bucket (console da Oracle) para o seu PC.
2. No seu PC, descriptografe com a chave privada:
   ```powershell
   age -d -i age-key.txt -o backup.dump meu-orcamento_AAAA-MM-DD_HHMM.dump.age
   ```
3. Envie para a VM (`scp`) e restaure (isso **substitui** os dados atuais):
   ```bash
   deploy/scripts/compose.sh stop api scheduler
   deploy/scripts/compose.sh exec -T db pg_restore --clean --if-exists --no-owner \
     -U orcamento -d orcamento < backup.dump
   deploy/scripts/compose.sh start api scheduler
   rm backup.dump
   ```

Faça um teste de restauração de vez em quando: backup que nunca foi restaurado não é garantia.

### Validar localmente antes (opcional, com Docker Desktop)

No PC, na pasta do projeto, crie um `.env.production` com `DOMAIN=localhost`,
`EMAIL_BACKEND=console` e uma chave age de teste. Depois:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

Abra `https://localhost` e aceite o aviso de certificado (o Caddy usa uma autoridade local
para `localhost`).

---

## Checklist de segurança

- [ ] Chave SSH da VM guardada fora do servidor; login por senha desligado (o script faz isso).
- [ ] Portas abertas na Oracle: só 22, 80 e 443.
- [ ] `.env.production` com `chmod 600` e uma cópia no gerenciador de senhas.
- [ ] Chave privada `age` fora do servidor, em dois lugares seguros.
- [ ] Bucket de backups **privado**.
- [ ] Deploy key do GitHub **sem** permissão de escrita.
- [ ] Chave do GitHub Actions restrita ao script de deploy (`command=...,restrict`).
- [ ] `frontend/src/legal.ts` preenchido (some o aviso de rascunho em Termos e Privacidade).
- [ ] Primeiro backup conferido no bucket e uma restauração de teste feita.
