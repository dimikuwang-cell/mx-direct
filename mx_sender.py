#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MX Direct 配套发信客户端 (Windows / Linux)
==========================================
- 导入发件箱: senders.txt 每行一个发件人邮箱 (可带 HELO域名,IP: 邮箱|helo域名|IP)
- 导入收件人: receivers.txt 每行一个邮箱
- 自动生成邮件头参数: 随机域名 / 随机大厂段IP / 7位SMTP ID / DKIM / Message-ID
- 多线程批量调用服务器 MX 直投接口

用法:
    python mx_sender.py --server http://23.94.63.137:8088 --token TOKEN ^
        --senders senders.txt --receivers receivers.txt ^
        --subject "标题" --body "正文文件或文本" --threads 20
"""
import argparse
import json
import os
import random
import sys
import threading
import time
import urllib.request

SAMPLE_DOMAINS = ["xzses.com", "codexses.com", "mailhub.top", "cloudmail.pro", "sendbox.net", "hpost.org"]
SAMPLE_IPS = ["8.8.8.8", "1.1.1.1", "13.107.42.14", "23.94.63.137", "34.120.72.0"]


def rand_hex(n):
    return "".join(random.choice("0123456789ABCDEF") for _ in range(n))


def rand_domain():
    return random.choice(SAMPLE_DOMAINS)


def rand_ip():
    return random.choice(SAMPLE_IPS)


def load_senders(path):
    """每行: 邮箱 或 邮箱|helo域名|IP  (# 注释 / 空行跳过)"""
    senders = []
    with open(path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            email = parts[0]
            if "@" not in email:
                continue
            senders.append({
                "email": email,
                "helo": parts[1] if len(parts) > 1 and parts[1] else "",
                "ip": parts[2] if len(parts) > 2 and parts[2] else "",
            })
    return senders


def load_lines(path):
    out = []
    if not path or not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                out.append(line)
    return out


def call_send(server, token, payload, timeout=40):
    req = urllib.request.Request(
        server.rstrip("/") + "/api/send",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {"error": str(e)}
    except Exception as e:
        return 0, {"error": str(e)}


def main():
    ap = argparse.ArgumentParser(description="MX Direct 发信客户端")
    ap.add_argument("--server", required=True, help="服务器地址, 如 http://23.94.63.137:8088")
    ap.add_argument("--token", required=True, help="服务器 API Token")
    ap.add_argument("--senders", required=True, help="发件箱文件 (每行 邮箱 或 邮箱|helo域名|IP)")
    ap.add_argument("--receivers", required=True, help="收件人文件 (每行一个邮箱)")
    ap.add_argument("--subject", default="", help="邮件主题")
    ap.add_argument("--body", default="", help="邮件正文文本, 或 @文件名")
    ap.add_argument("--threads", type=int, default=10, help="并发线程数")
    ap.add_argument("--delay", type=float, default=0.0, help="每封发送间隔秒数")
    ap.add_argument("--log", default="mx_send_result.csv", help="结果日志文件")
    args = ap.parse_args()

    senders = load_senders(args.senders)
    receivers = load_lines(args.receivers)
    if not senders:
        print("错误: 发件箱为空 (%s)" % args.senders)
        sys.exit(1)
    if not receivers:
        print("错误: 收件人为空 (%s)" % args.receivers)
        sys.exit(1)

    body_text = args.body
    if body_text.startswith("@"):
        with open(body_text[1:], "r", encoding="utf-8-sig") as f:
            body_text = f.read()

    print("发件箱: %d 个, 收件人: %d 个, 线程: %d" % (len(senders), len(receivers), args.threads))
    print("服务器: %s" % args.server)
    lock = threading.Lock()
    ok_count = 0
    fail_count = 0
    results = []
    start = time.time()

    def worker(idx, sender, to):
        nonlocal ok_count, fail_count
        if args.delay > 0:
            time.sleep(args.delay * idx)
        payload = {
            "to": to,
            "from_addr": sender["email"],
            "from_name": sender["email"].split("@")[0],
            "subject": args.subject,
            "body": body_text,
            "helo_domain": sender.get("helo") or ("mail." + rand_domain()),
            "fake_ip": sender.get("ip") or rand_ip(),
            "smtp_id": rand_hex(7),
        }
        status, resp = call_send(args.server, args.token, payload)
        ok = bool(resp.get("ok"))
        line = "%s,%s,%s,%s,%s" % (
            time.strftime("%Y-%m-%d %H:%M:%S"),
            to,
            sender["email"],
            "OK" if ok else "FAIL",
            resp.get("error", resp.get("mx", "")),
        )
        with lock:
            results.append(line)
            if ok:
                ok_count += 1
            else:
                fail_count += 1
        print("[%s] %s -> %s : %s" % ("OK" if ok else "FAIL", sender["email"], to, resp.get("error", resp.get("mx", ""))))

    threads = []
    idx = 0
    for i, to in enumerate(receivers):
        sender = senders[i % len(senders)]
        t = threading.Thread(target=worker, args=(idx, sender, to))
        idx += 1
        threads.append(t)
        t.start()
        if len(threads) >= args.threads:
            for t in threads:
                t.join()
            threads = []
    for t in threads:
        t.join()

    with open(args.log, "w", encoding="utf-8-sig") as f:
        f.write("时间,收件人,发件人,状态,详情\n")
        f.write("\n".join(results))

    cost = time.time() - start
    print("\n完成: 成功 %d, 失败 %d, 耗时 %.1fs, 日志: %s" % (ok_count, fail_count, cost, args.log))


if __name__ == "__main__":
    main()
