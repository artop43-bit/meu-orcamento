#!/usr/bin/env bash
# Prepara uma VM Ubuntu (22.04 ou 24.04, ARM ou x86) da Oracle Cloud para rodar o projeto.
# Rode UMA vez, logado como "ubuntu":   bash setup-server.sh
# Veja docs/DEPLOY.md, passo 4.
set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then
  echo "Rode como o usuário ubuntu (o script usa sudo quando precisa)." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

echo "==> Atualizando o sistema"
sudo apt-get update -q
sudo apt-get upgrade -yq
sudo apt-get install -yq ca-certificates curl git unattended-upgrades fail2ban iptables-persistent

echo "==> Atualizações de segurança automáticas"
sudo dpkg-reconfigure -f noninteractive unattended-upgrades

echo "==> Instalando o Docker (repositório oficial)"
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update -q
sudo apt-get install -yq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"
sudo systemctl enable --now docker

echo "==> Liberando HTTP e HTTPS no firewall da VM"
# As imagens Ubuntu da Oracle vêm com iptables bloqueando tudo exceto SSH (regra REJECT).
# As novas regras entram ANTES desse REJECT. (Também é preciso liberar 80/443 na
# Security List da VCN, no console da Oracle: veja docs/DEPLOY.md.)
reject_line() {
  sudo iptables -L INPUT --line-numbers -n | awk '$2 == "REJECT" { print $1; exit }'
}
allow() {
  local proto="$1" port="$2"
  if sudo iptables -C INPUT -p "$proto" --dport "$port" -m state --state NEW -j ACCEPT 2>/dev/null; then
    return
  fi
  local line
  line="$(reject_line)"
  if [ -n "$line" ]; then
    sudo iptables -I INPUT "$line" -p "$proto" --dport "$port" -m state --state NEW -j ACCEPT
  else
    sudo iptables -A INPUT -p "$proto" --dport "$port" -m state --state NEW -j ACCEPT
  fi
}
allow tcp 80
allow tcp 443
allow udp 443  # HTTP/3
sudo netfilter-persistent save

echo "==> Endurecendo o SSH (somente chave, sem root)"
sudo tee /etc/ssh/sshd_config.d/99-meu-orcamento.conf > /dev/null <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
EOF
sudo systemctl reload ssh || sudo systemctl reload sshd

echo "==> fail2ban para o SSH"
sudo tee /etc/fail2ban/jail.d/sshd.local > /dev/null <<'EOF'
[sshd]
enabled = true
maxretry = 5
bantime = 1h
EOF
sudo systemctl enable --now fail2ban
sudo systemctl restart fail2ban

echo
echo "Pronto. Saia e entre de novo no SSH para usar o docker sem sudo."
echo "Próximo passo: clonar o repositório (docs/DEPLOY.md, passo 5)."
