#!/bin/bash
# EC2 user-data. Amazon Linux 2023 전용.
# AL2023 은 SSM 에이전트와 aws CLI 가 기본 탑재라 docker · compose · git 만 깐다.
set -euxo pipefail

# 스왑 2GB. t3.medium(4GB) 에서 AI 이미지를 빌드하면 torch 설치와
# 임베딩 1,609조각 계산이 겹쳐 메모리가 빡빡하다. 보험으로 둔다.
if [ ! -f /swapfile ]; then
  dd if=/dev/zero of=/swapfile bs=1M count=2048
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

dnf update -y
dnf install -y docker git jq

systemctl enable --now docker
usermod -aG docker ec2-user

# compose 플러그인은 AL2023 리포에 없다. 릴리스 바이너리를 받는다.
PLUGIN_DIR=/usr/local/lib/docker/cli-plugins
mkdir -p "$PLUGIN_DIR"
COMPOSE_VER="$(curl -fsSL https://api.github.com/repos/docker/compose/releases/latest \
  | jq -r '.tag_name' 2>/dev/null || true)"
if [ -z "$COMPOSE_VER" ] || [ "$COMPOSE_VER" = "null" ]; then
  COMPOSE_VER=v2.39.1     # GitHub API 레이트리밋에 걸렸을 때의 폴백
fi
curl -fsSL "https://github.com/docker/compose/releases/download/${COMPOSE_VER}/docker-compose-linux-$(uname -m)" \
  -o "$PLUGIN_DIR/docker-compose"
chmod +x "$PLUGIN_DIR/docker-compose"

install -d -o ec2-user -g ec2-user /opt/settle

docker --version
docker compose version
echo "bootstrap done"
