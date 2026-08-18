# MX Direct 邮件直投系统

一键部署到 Ubuntu 的直投发信系统 + Windows 配套批量发送脚本 + Cloudflare 一键 DNS 解析。

## 功能

- 导入收件箱 (receivers.txt) / 发件箱 (senders.txt, 发件人是域名邮箱)
- 自动解析收件人 MX 并直连 MX:25 投递 (dig / nslookup / DoH 三级回退)
- 注入自定义 Received 头 (随机域名 + 随机大厂段 IP + 7位随机 SMTP ID)
- 真实 DKIM 签名 (dkimpy, h 覆盖 from/to/subject/date/message-id)
- 自动生成 Message-ID / Date 头
- 一键发布 DNS 记录 (A / MX / SPF / DKIM / DMARC) 到 Cloudflare

## 架构

```
Windows 客户端 (mx_sender.py)          Ubuntu 服务器 (mx_direct_server.py)
  |- 导入发件箱 senders.txt               |- HTTP API :8088 (Bearer Token)
  |- 导入收件人 receivers.txt             |- 自动查收件人 MX
  |- 随机生成头参数 (域名/IP/ID)          |- 直连 MX:25 投递 (EHLO=随机域名)
  +- 多线程 POST /api/send                +- 注入 Received / 真实DKIM / Message-ID

DNS 解析 (dns_setup.py, Windows 执行)
  +- 从服务器 /api/dkim 取公钥 -> Cloudflare 发布 A/MX/SPF/DKIM/DMARC -> DoH 验证
```

## 1. 服务器部署 (Ubuntu)

```bash
sudo bash install.sh                      # 默认域名 codexses.com
sudo bash install.sh codexses.com 23.94.63.137
```

完成后:
- 服务: `mx-direct` (systemd, 开机自启, 监听 0.0.0.0:8088)
- Token: `cat /opt/mx_direct/mx_direct_config.json`
- DKIM 私钥: `/opt/mx_direct/dkim.private.key` (首次启动自动生成)
- 验证: `curl http://<IP>:8088/health`

> 改端口/域名池/Token: 编辑 `/opt/mx_direct/mx_direct_config.json` 后 `systemctl restart mx-direct`

## 2. 一键 DNS 解析 (Cloudflare)

```bash
# 需要 Cloudflare API Token (Zone Read + DNS Edit 权限)
python dns_setup.py --domain codexses.com --server-ip 23.94.63.137 ^
    --api http://<服务器IP>:8088 --token <MX-API-Token> ^
    --cf-token <Cloudflare-Token> --verify
```

发布记录:
| 类型 | 名称 | 内容 |
|---|---|---|
| A | mail | 服务器IP |
| MX | @ | mail.域名 (10) |
| TXT | @ | v=spf1 ip4:服务器IP ~all |
| TXT | dkim._domainkey | v=DKIM1; k=rsa; p=... (自动取自服务器) |
| TXT | _dmarc | v=DMARC1; p=none; rua=mailto:postmaster@域名; |

参数: `--records a,mail,mx,spf,dkim,dmarc` 可选择发布项; `--dry-run` 只预览; `--verify` 发布后 DoH 验证生效。

## 3. Windows 批量发送

```bash
# 发件箱 senders.txt (每行一个域名邮箱, 可带 邮箱|HELO域名|IP)
sender@codexses.com|mail.xzses.com|8.8.8.8
marketing@codexses.com

# 收件人 receivers.txt (每行一个邮箱)
user1@qq.com
user2@163.com

python mx_sender.py --server http://<服务器IP>:8088 --token <TOKEN> ^
    --senders senders.txt --receivers receivers.txt ^
    --subject "主题" --body @body.txt --threads 20
```

| 参数 | 说明 |
|---|---|
| `--server` | 服务器地址 |
| `--token` | API Token |
| `--senders` | 发件箱文件 (域名邮箱) |
| `--receivers` | 收件人文件 |
| `--subject` | 主题 |
| `--body` | 正文, 或 @文件名 |
| `--threads` | 并发数 (默认10) |
| `--delay` | 每封间隔秒 |
| `--log` | 结果日志 csv |

## 生成的邮件头 (每封自动, Received 强制最上方)

```
Received: from 随机域名 (随机域名 [随机大厂段IP])
	by 收件人MX (NewMX) with SMTP id 7位随机ID
	for <收件人>; 星期几, 日期 时间
DKIM-Signature: v=1; a=rsa-sha256; c=relaxed/relaxed; d=发件域名; s=dkim; ...
	 h=from : to : subject : date : message-id : mime-version : content-type
Message-ID: <随机@随机域名>
Date: RFC2822 时间
From: 发件人 <sender@域名>
To: 收件人
Subject: 主题
```

## 服务器 API

| 接口 | 方法 | 说明 |
|---|---|---|
| /health | GET | 健康检查 |
| /api/send | POST | 投递邮件 (需 Bearer Token) |
| /api/dkim | GET | 获取 DKIM 公钥 TXT (需 Bearer Token) |

POST /api/send 请求体:
```json
{
  "to": "user@qq.com",
  "from_addr": "sender@codexses.com",
  "from_name": "可选显示名",
  "subject": "主题",
  "body": "正文",
  "helo_domain": "可选, 留空随机",
  "fake_ip": "可选, 留空随机",
  "smtp_id": "可选, 留空随机7位",
  "by_mx": "可选, 留空自动查收件人MX"
}
```


## 4. 图形界面发送软件 (Windows)

```bash
# 源码运行
python mx_sender_gui.py

# 或直接运行编译好的程序
dist/MXSender/MXSender.exe
```

- 顶部填服务器地址 / Token, 可测试连接; 配置自动保存到 mx_sender_gui_config.json
- 发件箱/收件人支持 TXT 导入 (发件箱每行: 邮箱 或 邮箱|HELO域名|IP)
- 主题 + 正文, 支持纯文本 / HTML 切换与浏览器预览
- 高级参数留空 = 服务器自动随机 (随机域名/IP/7位SMTP ID)
- 多线程批量发送 + 进度条 + 实时日志 + 结果 CSV (发送结果_时间.csv)

## 说明

- 注入头里的 IP 为显示用途; 收件方 MX 实际看到的 TCP 源 IP 是服务器 IP (邮件系统物理规则)
- 真实 DKIM 需先发布 `dkim._domainkey.<域名>` 的 TXT 公钥 (见第 2 步), 否则验签 fail
- 若 dkimpy 未安装, 自动回退为格式完整的占位 DKIM 头
