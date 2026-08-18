#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MX Direct 直投邮件服务器
========================
- HTTP 接口接收发信请求 (POST /api/send, Bearer Token 认证)
- 自动查询收件人 MX, 直连 MX:25 投递
- 投递时 EHLO 使用随机域名, 并在邮件最上方注入自定义 Received 头
- 自动生成 DKIM-Signature / Message-ID / Date 头
- 纯 Python 标准库, 无需 pip 安装 (仅依赖系统 dig 命令查 MX)

部署 (Ubuntu):
    bash install.sh
配置文件: mx_direct_config.json  (token 首次启动自动生成)
"""
import json
import os
import random
import secrets
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import smtplib

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "mx_direct_config.json")
LOG_PATH = os.path.join(BASE_DIR, "mx_direct.log")

DEFAULT_CONFIG = {
    "listen": "0.0.0.0",
    "port": 8088,
    "token": "",
    "timeout": 30,
    "helo_domains": ["xzses.com", "codexses.com", "mailhub.top", "cloudmail.pro", "sendbox.net"],
    "use_real_dkim": False,
    "dkim_private_key": "/opt/mx_direct/dkim.private.key",
    "dkim_selector": "dkim",
    "dkim_domain": "codexses.com",
}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                cfg.update(loaded)
        except Exception:
            pass
    if not cfg.get("token"):
        cfg["token"] = secrets.token_urlsafe(24)
        save_config(cfg)
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


CONFIG = load_config()


def log(msg):
    line = "[%s] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ---------------- 工具函数 ----------------
def rand_hex(n):
    return "".join(random.choice("0123456789ABCDEF") for _ in range(n))


def rand_b64(n):
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    return "".join(random.choice(chars) for _ in range(n))


def rand_ip():
    # 随机公网 IP (注入头用, 非真实出站 IP)
    return "%d.%d.%d.%d" % (
        random.choice([8, 13, 23, 34, 35, 43, 47, 52, 54, 64, 66, 104, 108, 146, 152, 154, 172, 182, 185, 203]),
        random.randint(0, 254),
        random.randint(0, 254),
        random.randint(1, 254),
    )


def rand_helo(domains):
    if domains:
        d = random.choice([x for x in domains if x])
        return "%s.%s" % (random.choice(["mail", "mx", "smtp", "send", "post", "cloud", "box", "relay"]), d)
    return "mail.example.com"


def rfc2822_cn(dt=None):
    # RFC 2822 +0800 格式: Sat, 15 Aug 2026 01:00:36 +0800
    if dt is None:
        dt = datetime.now(timezone(timedelta(hours=8)))
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return "%s, %02d %s %04d %02d:%02d:%02d +0800" % (
        days[dt.weekday()], dt.day, months[dt.month - 1], dt.year,
        dt.hour, dt.minute, dt.second,
    )


def _parse_mx_lines(lines):
    mxs = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[0].lstrip("-").isdigit():
            mxs.append((int(parts[0]), parts[-1].rstrip(".")))
        low = line.lower()
        if "mail exchanger" in low and "=" in line:
            host = line.rsplit("=", 1)[1].strip().rstrip(".")
            if host and host.lower() != "mail exchanger":
                mxs.append((10, host))
    mxs.sort()
    return mxs


def query_mx(domain):
    """按优先级排序的 MX 列表 [(prio, host), ...]; dig / nslookup / DoH 三级回退"""
    # 1) dig (Linux)
    try:
        out = subprocess.run(
            ["dig", "+short", "MX", domain], capture_output=True, text=True, timeout=15
        ).stdout
        mxs = _parse_mx_lines(out.splitlines())
        if mxs:
            return mxs
    except Exception:
        pass
    # 2) nslookup (Windows / macOS)
    try:
        out = subprocess.run(
            ["nslookup", "-type=MX", domain], capture_output=True, text=True, timeout=15
        ).stdout
        mxs = _parse_mx_lines(out.splitlines())
        if mxs:
            return mxs
    except Exception:
        pass
    # 3) DoH (dns.google) 跨平台回退
    try:
        from urllib.parse import quote
        from urllib.request import urlopen
        url = "https://dns.google/resolve?name=%s&type=MX" % quote(domain)
        with urlopen(url, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        mxs = []
        for a in payload.get("Answer", []):
            data = a.get("data", "").strip()
            parts = data.split()
            if len(parts) >= 2 and parts[0].lstrip("-").isdigit():
                mxs.append((int(parts[0]), parts[-1].rstrip(".")))
        mxs.sort()
        return mxs
    except Exception as e:
        log("MX 查询失败 %s: %s" % (domain, e))
        return []


def fake_dkim(domain, selector="dkim"):
    t = int(time.time())
    return (
        "DKIM-Signature: v=1; a=rsa-sha256; c=relaxed/relaxed; d=%s; s=%s; t=%d; "
        "h=from:to:subject:message-id; bh=%s; b=%s" % (
            domain, selector, t, rand_b64(44), rand_b64(80)
        )
    )



def ensure_dkim_keys():
    """启动时确保 DKIM 私钥存在 (无则 openssl 生成)"""
    priv = CONFIG.get("dkim_private_key") or os.path.join(BASE_DIR, "dkim.private.key")
    if not os.path.exists(priv):
        try:
            subprocess.run(
                ["openssl", "genrsa", "-out", priv, "2048"],
                check=True, capture_output=True, timeout=30,
            )
            CONFIG["dkim_private_key"] = priv
            save_config(CONFIG)
            log("已生成 DKIM 私钥: %s" % priv)
        except Exception as e:
            log("生成 DKIM 私钥失败: %s" % e)
    return priv


def get_dkim_public_txt():
    """从私钥提取公钥并格式化为 TXT 记录值"""
    priv = ensure_dkim_keys()
    try:
        p = subprocess.run(
            ["openssl", "rsa", "-in", priv, "-pubout", "-outform", "DER"],
            capture_output=True, timeout=20,
        )
        b64 = subprocess.run(
            ["openssl", "base64", "-A"], input=p.stdout, capture_output=True, timeout=20
        ).stdout.decode("utf-8", "replace").strip()
        return "v=DKIM1; k=rsa; p=%s" % b64
    except Exception as e:
        log("提取 DKIM 公钥失败: %s" % e)
        return ""


def real_dkim_sign(msg_bytes, domain, selector, priv_path):
    """真实 DKIM 签名 (需要 pip install dkimpy); 失败返回 None"""
    try:
        import dkim
    except Exception:
        return None
    try:
        with open(priv_path, "rb") as f:
            priv = f.read()
        return dkim.sign(
            msg_bytes,
            selector.encode("ascii"),
            domain.encode("ascii"),
            priv,
            canonicalize=(b"relaxed", b"relaxed"),
            include_headers=[
                b"from", b"to", b"subject", b"date",
                b"message-id", b"mime-version", b"content-type",
            ],
        )
    except Exception as e:
        log("DKIM 签名失败: %s" % e)
        return None


def build_message(req):
    """构造完整邮件文本 (头 + 正文), 返回 (msg, helo, fake_ip, smtp_id, by_mx)

    头顺序: Received (最上方) -> DKIM-Signature -> Message-ID/Date/From/To/... -> 正文
    真实 DKIM: 先构建不含 DKIM 的完整头部再签名, 确保 h= 覆盖
    from/to/subject/date/message-id 等字段, 收件方 MX 才能验签通过.
    """
    to = str(req.get("to", "")).strip()
    from_addr = str(req.get("from_addr", "")).strip() or "noreply@example.com"
    from_name = str(req.get("from_name", "")).strip()
    subject = str(req.get("subject", "")).strip()
    body = str(req.get("body", "")).strip()
    is_html = bool(req.get("html"))
    helo_domains = CONFIG.get("helo_domains") or DEFAULT_CONFIG["helo_domains"]
    helo = str(req.get("helo_domain", "")).strip() or rand_helo(helo_domains)
    fake_ip = str(req.get("fake_ip", "")).strip() or rand_ip()
    smtp_id = str(req.get("smtp_id", "")).strip() or rand_hex(7)
    ts = rfc2822_cn()

    to_domain = to.split("@")[-1] if "@" in to else ""
    by_mx = str(req.get("by_mx", "")).strip()
    if not by_mx:
        mxs = query_mx(to_domain)
        by_mx = mxs[0][1] if mxs else (to_domain or "unknown")

    msg_id = str(req.get("message_id", "")).strip() or "<%s%d@%s>" % (rand_hex(12), int(time.time()), helo)

    received = (
        "Received: from %s (%s [%s])\r\n"
        "\tby %s (NewMX) with SMTP id %s\r\n"
        "\tfor <%s>; %s" % (helo, helo, fake_ip, by_mx, smtp_id, to, ts)
    )

    # From 头 (含中文发件名时编码)
    if from_name:
        try:
            from email.header import Header
            from_header = "From: %s <%s>" % (Header(from_name, "utf-8").encode(), from_addr)
        except Exception:
            from_header = "From: %s <%s>" % (from_name, from_addr)
    else:
        from_header = "From: %s" % from_addr

    # 1) 先构建不含 DKIM 的完整头部, 用其签名
    signed_headers = [
        received,
        "Message-ID: %s" % msg_id,
        "Date: %s" % ts,
        from_header,
        "To: %s" % to,
        "Subject: %s" % subject,
        "MIME-Version: 1.0",
        'Content-Type: text/html; charset="utf-8"' if is_html else 'Content-Type: text/plain; charset="utf-8"',
        "Content-Transfer-Encoding: 8bit",
    ]
    msg_for_sign = "\r\n".join(signed_headers) + "\r\n\r\n" + body

    dkim_domain = str(CONFIG.get("dkim_domain") or "").strip() or (from_addr.split("@")[-1] if "@" in from_addr else "")
    dkim_header = None
    if CONFIG.get("use_real_dkim") and dkim_domain:
        sig = real_dkim_sign(msg_for_sign.encode("utf-8"), dkim_domain, CONFIG.get("dkim_selector", "dkim"), ensure_dkim_keys())
        if sig:
            dkim_header = sig.decode("utf-8", "replace").strip()
    if not dkim_header:
        dkim_header = fake_dkim(dkim_domain or (helo.split("@")[-1] if "@" in helo else helo), CONFIG.get("dkim_selector", "dkim"))

    # 2) 最终顺序: Received -> DKIM-Signature -> 其余头部
    # 最终顺序: Received (强制第一行) -> DKIM-Signature -> 其余头部
    headers = [received, dkim_header] + signed_headers[1:]
    msg = "\r\n".join(headers) + "\r\n\r\n" + body

    # 防御: 无论任何原因导致头部顺序变化, 强制 Received 回到最顶端
    if not msg.startswith("Received:"):
        parts = msg.split("\r\n", 1)
        msg = received + ("\r\n" + parts[1] if len(parts) == 2 else "")

    return msg, helo, fake_ip, smtp_id, by_mx


def deliver(mxs, from_addr, to, msg, helo, timeout):
    last_err = ""
    for _prio, host in mxs:
        try:
            log("直投 %s -> %s (EHLO=%s)" % (from_addr, host, helo))
            smtp = smtplib.SMTP(host, 25, timeout=timeout, local_hostname=helo)
            smtp.ehlo(helo)
            smtp.sendmail(from_addr, [to], msg.encode("utf-8"))
            smtp.quit()
            return True, host
        except Exception as e:
            last_err = str(e)
            log("投递 %s 失败: %s" % (host, last_err))
            continue
    return False, last_err


# ---------------- HTTP 接口 ----------------
class Handler(BaseHTTPRequestHandler):
    server_version = "MXDirect/1.0"

    def log_message(self, fmt, *args):
        log("%s %s" % (self.address_string(), fmt % args))

    def _json(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _check_auth(self):
        auth = self.headers.get("Authorization", "")
        if auth == "Bearer " + CONFIG.get("token", ""):
            return True
        self._json(401, {"ok": False, "error": "unauthorized"})
        return False

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"ok": True, "service": "mx-direct", "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        elif self.path == "/api/dkim":
            if not self._check_auth():
                return
            domain = str(CONFIG.get("dkim_domain") or "").strip()
            selector = str(CONFIG.get("dkim_selector") or "dkim").strip()
            self._json(200, {
                "ok": True,
                "domain": domain,
                "selector": selector,
                "record": "%s._domainkey.%s" % (selector, domain) if domain else "",
                "txt": get_dkim_public_txt(),
            })
        else:
            self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if self.path != "/api/send":
            self._json(404, {"ok": False, "error": "not found"})
            return
        if not self._check_auth():
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception as e:
            self._json(400, {"ok": False, "error": "bad request: %s" % e})
            return

        to = str(req.get("to", "")).strip()
        if not to or "@" not in to:
            self._json(400, {"ok": False, "error": "invalid to"})
            return
        try:
            msg, helo, fake_ip, smtp_id, by_mx = build_message(req)
            to_domain = to.split("@")[-1]
            mxs = query_mx(to_domain)
            if not mxs:
                self._json(502, {"ok": False, "error": "no MX for %s" % to_domain})
                return
            ok, info = deliver(mxs, str(req.get("from_addr", "")).strip() or "noreply@example.com",
                               to, msg, helo, CONFIG.get("timeout", 30))
            if ok:
                self._json(200, {"ok": True, "mx": info, "helo": helo, "smtp_id": smtp_id, "by_mx": by_mx})
            else:
                self._json(502, {"ok": False, "error": "delivery failed: %s" % info, "mx": ", ".join(h for _, h in mxs)})
        except Exception as e:
            log("发送异常: %s" % e)
            self._json(500, {"ok": False, "error": str(e)})


def main():
    try:
        server = ThreadingHTTPServer((CONFIG["listen"], int(CONFIG["port"])), Handler)
    except Exception as e:
        print("启动失败: %s" % e, file=sys.stderr)
        sys.exit(1)
    log("MX Direct 服务启动: http://%s:%s (token=%s)" % (CONFIG["listen"], CONFIG["port"], CONFIG["token"]))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
