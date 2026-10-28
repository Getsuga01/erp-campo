#!/usr/bin/env bash
# =============================================================================
# Projeto 2 (demo fictícia) — setup da VM de deploy online
# Alvo: Ubuntu 22.04+ ARM (Oracle Cloud Always Free, VM.Standard.A1.Flex)
#
# O que este script faz (idempotente):
#   1. Instala o Docker (se ausente)
#   2. Gera .env com chaves de API fortes (as do README são públicas!)
#   3. Gera db-deploy/ a partir de db/ — transformação XEPDB1 -> FREEPDB1
#      (a imagem Oracle 23ai Free usada no deploy tem PDB com outro nome)
#   4. Sobe a stack com docker-compose.deploy.yml
#   5. Instala o cloudflared e imprime os passos do tunnel (parte manual)
#
# Uso (na VM, como root ou com sudo):
#   sudo bash deploy/setup-vm.sh
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."

# --- 1) Docker ---------------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
    echo "==> instalando Docker"
    curl -fsSL https://get.docker.com | sh
else
    echo "==> Docker ja instalado: $(docker --version)"
fi

# --- 2) .env com chaves fortes (as chaves do README sao publicas) -------------
if [ ! -f .env ]; then
    echo "==> gerando .env com chaves aleatorias (openssl rand -hex)"
    {
        echo "# Gerado por deploy/setup-vm.sh em $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
        echo "ORACLE_PASSWORD=$(openssl rand -hex 12)"
        echo "CAMPO_API_KEY=$(openssl rand -hex 16)"
        echo "INT_API_KEY=$(openssl rand -hex 16)"
        echo ""
        echo "# Senhas ficticias do banco (1521 nao publicado fora do compose):"
        echo "# defaults de .env.example. Para troca real, ver db/01_schema.sql."
        echo "INT_ORACLE_SENHA=IntegracaoFicticia2026"
        echo "PAINEL_ORACLE_SENHA=IntegracaoFicticia2026"
    } > .env
    chmod 600 .env
    echo "    .env criado (mantenha-o fora do git — ja esta no .gitignore)"
else
    echo "==> .env ja existe — mantendo o atual"
fi

# --- 3) db-deploy: scripts SQL com PDB FREEPDB1 (imagem 23ai/ARM) ------------
echo "==> gerando db-deploy/ a partir de db/ (XEPDB1 -> FREEPDB1)"
mkdir -p db-deploy
for arquivo in db/*.sql; do
    sed 's/XEPDB1/FREEPDB1/g' "$arquivo" > "db-deploy/$(basename "$arquivo")"
done
# Fail fast: a transformacao e a base do init do banco — nao pode falhar calada.
if grep -rq 'XEPDB1' db-deploy/; then
    echo "ERRO: ainda ha XEPDB1 em db-deploy/ — transformacao falhou" >&2
    exit 1
fi
if ! grep -q 'FREEPDB1' db-deploy/01_schema.sql; then
    echo "ERRO: FREEPDB1 ausente em db-deploy/01_schema.sql — transformacao falhou" >&2
    exit 1
fi
echo "    ok: $(ls db-deploy | wc -l) scripts prontos (nao edite db-deploy — regenere)"

# --- 4) Subir a stack ----------------------------------------------------------
echo "==> docker compose -f docker-compose.deploy.yml up -d --build"
docker compose -f docker-compose.deploy.yml up -d --build
docker compose -f docker-compose.deploy.yml ps
echo "    aguarde o Oracle ficar (healthy) — no 1o boot os scripts de init"
echo "    demoram alguns minutos; depois o painel responde em http://127.0.0.1:8501"

# --- 5) cloudflared (tunnel HTTPS sem abrir portas) -----------------------------
if ! command -v cloudflared >/dev/null 2>&1; then
    echo "==> instalando cloudflared"
    mkdir -p --mode=0755 /usr/share/keyrings
    curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
        | tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
    echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' \
        | tee /etc/apt/sources.list.d/cloudflared.list >/dev/null
    apt-get update -qq && apt-get install -y -qq cloudflared
else
    echo "==> cloudflared ja instalado: $(cloudflared --version)"
fi

cat <<'FIM'
==> PROXIMOS PASSOS (one-time; exigem sua conta Cloudflare — com domínio próprio
    ou um gratuito, ex.: no próprio Cloudflare Registrar):

  1) cloudflared tunnel login
  2) cloudflared tunnel create campo-erp
  3) cloudflared tunnel route dns campo-erp painel.SEU-DOMINIO
  4) crie /etc/cloudflared/config.yml:
       tunnel: <ID impresso no passo 2>
       credentials-file: /root/.cloudflared/<ID>.json
       ingress:
         - hostname: painel.SEU-DOMINIO
           service: http://localhost:8501
         - service: http_status:404
  5) cloudflared service install && systemctl enable --now cloudflared

==> SEGURANCA OBRIGATORIA: o painel não tem autenticação própria (interno por
    design). Antes de divulgar a URL, proteja-a com Cloudflare Access:
    Zero Trust > Access > Applications > Add self-hosted >
      hostname painel.SEU-DOMINIO com policy "Allow" por e-mail dos testers.
FIM
