#!/bin/bash
# MX Direct 邮件直投服务 一键安装 (Ubuntu 20.04 / 22.04 / 24.04)
# 用法: sudo bash install.sh [--domain 发件域名] [--server-ip 服务器IP]
set -e

APP_DIR=/opt/mx_direct
PYTHON=/usr/bin/python3
DOMAIN=${1:-codexses.com}
SERVER_IP=${2:-$(curl -4 -s ifconfig.me || hostname -I | awk '{print $1}')}

echo "==> 1/5 检查依赖 (dig / python3 / openssl)"
for c in dig python3 openssl curl; do
  if ! command -v $c >/dev/null 2>&1; then
    apt-get update -y
    apt-get install -y dnsutils python3 openssl curl
    break
  fi
done

echo "==> 1b/5 安装 dkimpy (真实 DKIM 签名)"
if ! $PYTHON -c "import dkim" >/dev/null 2>&1; then
  apt-get install -y python3-pip >/dev/null 2>&1 || true
  $PYTHON -m pip install --break-system-packages dkimpy >/dev/null 2>&1 || $PYTHON -m pip install dkimpy >/dev/null 2>&1 || echo "警告: dkimpy 安装失败, 将使用占位 DKIM 头"
fi

echo "==> 2/5 复制程序 + 生成配置"
mkdir -p "$APP_DIR"
cp -f "$(dirname "$0")/mx_direct_server.py" "$APP_DIR/mx_direct_server.py"
if [ ! -f "$APP_DIR/mx_direct_config.json" ]; then
  cat > "$APP_DIR/mx_direct_config.json" <<EOF
{
  "listen": "0.0.0.0",
  "port": 8088,
  "token": "",
  "timeout": 30,
  "helo_domains": ["xzses.com", "codexses.com", "mailhub.top", "cloudmail.pro", "sendbox.net"],
  "use_real_dkim": true,
  "dkim_private_key": "/opt/mx_direct/dkim.private.key",
  "dkim_selector": "dkim",
  "dkim_domain": "$DOMAIN"
}
EOF
fi
chmod +x "$APP_DIR/mx_direct_server.py"

echo "==> 2b/5 生成 DKIM 私钥 (如缺失)"
if [ ! -f "$APP_DIR/dkim.private.key" ]; then
  openssl genrsa -out "$APP_DIR/dkim.private.key" 2048 >/dev/null 2>&1
  chmod 600 "$APP_DIR/dkim.private.key"
  echo "    已生成 DKIM 私钥: $APP_DIR/dkim.private.key"
fi

echo "==> 3/5 注册 systemd 服务"
cat > /etc/systemd/system/mx-direct.service <<EOF
[Unit]
Description=MX Direct Mail Server
After=network.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR
ExecStart=$PYTHON $APP_DIR/mx_direct_server.py
Restart=always
RestartSec=3
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable mx-direct >/dev/null 2>&1 || true
systemctl restart mx-direct
sleep 2

echo "==> 4/5 检查状态"
systemctl is-active mx-direct
if command -v ufw >/dev/null 2>&1; then
  ufw allow 8088/tcp >/dev/null 2>&1 || true
  echo "已放行 8088/tcp (ufw)"
fi

TOKEN=$(grep -oP '(?<="token": ")[^"]+' "$APP_DIR/mx_direct_config.json" 2>/dev/null || echo "(查看配置文件)")

echo "==> 5/5 获取 DKIM 公钥"
sleep 2
DKIM_TXT=$(curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8088/api/dkim | $PYTHON -c "import sys,json;print(json.load(sys.stdin).get('txt',''))" 2>/dev/null || echo "")

echo ""
echo "============================================================"
echo " MX Direct 部署完成!"
echo " API:        http://<服务器IP>:8088"
echo " TOKEN:      $TOKEN"
echo " 日志:       $APP_DIR/mx_direct.log"
echo " 测试:       curl http://<服务器IP>:8088/health"
echo " 发信测试:   curl -X POST http://<服务器IP>:8088/api/send -H 'Authorization: Bearer $TOKEN' -H 'Content-Type: application/json' -d '{"to": "you@qq.com", "from_addr": "sender@$DOMAIN", "subject": "test", "body": "hello"}'"
echo ""
echo " 一键 DNS 解析 (Cloudflare, 在 Windows 上执行):"
echo "   python dns_setup.py --domain $DOMAIN --server-ip $SERVER_IP \\"
echo "       --api http://<服务器IP>:8088 --token $TOKEN --cf-token <Cloudflare-Token> --verify"
echo ""
if [ -n "$DKIM_TXT" ]; then
  echo " DKIM TXT 记录 (dkim._domainkey.$DOMAIN):"
  echo "   \"$DKIM_TXT\""
fi
echo "============================================================"
