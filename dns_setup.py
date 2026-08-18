#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MX Direct 一键 DNS 解析 (Cloudflare)
====================================
- 从服务器 /api/dkim 获取真实 DKIM 公钥
- 自动发布: A(mail) / MX / SPF / DKIM / DMARC 到 Cloudflare
- TXT 值统一加双引号, 已存在的记录自动更新/跳过
- 发布后自动用 DoH 验证生效

依赖: 仅 Python 标准库 (urllib), Windows / Linux 通用

用法:
    python dns_setup.py --domain codexses.com --server-ip 23.94.63.137 ^
        --api http://23.94.63.137:8088 --token <MX-API-Token> ^
        --cf-token <Cloudflare-API-Token> [--dry-run]
"""
import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
import io

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

CF_API = "https://api.cloudflare.com/client/v4"
DOH_SERVERS = ["https://dns.google/resolve", "https://cloudflare-dns.com/dns-query"]


def http_json(url, headers=None, payload=None, method=None, timeout=25):
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"))
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(raw)
            except Exception:
                return resp.status, {"raw": raw}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw}
    except Exception as e:
        return 0, {"error": str(e)}


# ---------------- Cloudflare ---------------- #
class Cloudflare(object):
    def __init__(self, token, dry_run=False):
        self.token = token
        self.dry_run = dry_run
        self._zone_cache = {}

    def _call(self, method, path, body=None):
        headers = {
            "Authorization": "Bearer " + self.token,
            "Content-Type": "application/json",
            "User-Agent": "MXDirect/1.0",
        }
        code, payload = http_json(CF_API + path, headers=headers, payload=body, method=method)
        if code >= 400 or not payload.get("success"):
            msgs = "; ".join(e.get("message", str(e)) for e in payload.get("errors", [])) or payload.get("raw", payload)
            raise RuntimeError("Cloudflare 错误 [%s]: %s" % (code, msgs))
        return payload.get("result")

    def zone_id(self, domain):
        if domain in self._zone_cache:
            return self._zone_cache[domain]
        result = self._call("GET", "/zones?name=%s&status=active" % urllib.parse.quote(domain))
        if not result:
            raise RuntimeError("Cloudflare 找不到域名 %s 的 Zone (请确认域名已接入且 Token 有 Zone Read 权限)" % domain)
        self._zone_cache[domain] = result[0]["id"]
        return self._zone_cache[domain]

    def list_records(self, domain):
        zone = self.zone_id(domain)
        return self._call("GET", "/zones/%s/dns_records?per_page=100" % zone) or []

    def _find(self, domain, rtype, name):
        full = domain if name in ("@", "", ".") else "%s.%s" % (name, domain)
        for r in self.list_records(domain):
            if str(r.get("type", "")).upper() == rtype.upper() and str(r.get("name", "")).lower() == full.lower():
                return r
        return None

    def upsert(self, domain, rtype, name, value, priority=None, ttl=600):
        zone = self.zone_id(domain)
        full = domain if name in ("@", "", ".") else "%s.%s" % (name, domain)
        body = {"type": rtype.upper(), "name": full, "content": value, "ttl": ttl, "proxied": False}
        if rtype.upper() == "MX":
            body["priority"] = int(priority if priority is not None else 10)
        existing = self._find(domain, rtype, name)
        if self.dry_run:
            action = "skip" if existing else "create"
            print("  [dry-run] %s %s -> %s (%s)" % (rtype.upper(), full, value, action))
            return {"action": action, "id": existing.get("id") if existing else None}
        if existing:
            old = str(existing.get("content", "")).strip('"')
            old_prio = str(existing.get("priority", "10"))
            new_prio = str(int(priority if priority is not None else 10))
            if old.strip('"') == str(value).strip('"') and (rtype.upper() != "MX" or old_prio == new_prio):
                print("  [skip] %s %s 已存在且内容一致" % (rtype.upper(), full))
                return {"action": "skipped", "id": existing.get("id")}
            rid = existing.get("id")
            self._call("PUT", "/zones/%s/dns_records/%s" % (zone, rid), body)
            print("  [update] %s %s -> %s" % (rtype.upper(), full, value))
            return {"action": "updated", "id": rid}
        result = self._call("POST", "/zones/%s/dns_records" % zone, body)
        print("  [create] %s %s -> %s" % (rtype.upper(), full, value))
        return {"action": "created", "id": result.get("id")}


# ---------------- 记录构建 ---------------- #
def quoted(v):
    v = str(v).strip()
    if v.startswith('"') and v.endswith('"'):
        return v
    return '"%s"' % v


def build_records(domain, server_ip, dkim_txt):
    mail_host = "mail.%s" % domain
    records = [
        {"key": "a",     "rtype": "A",  "name": "@",              "value": server_ip,                                     "prio": None, "desc": "主域 A 记录"},
        {"key": "mail",  "rtype": "A",  "name": "mail",           "value": server_ip,                                     "prio": None, "desc": "mail 主机 A 记录"},
        {"key": "mx",    "rtype": "MX", "name": "@",              "value": mail_host,                                     "prio": 10,   "desc": "主域 MX -> mail 主机"},
        {"key": "spf",   "rtype": "TXT","name": "@",              "value": "v=spf1 ip4:%s ~all" % server_ip,             "prio": None, "desc": "SPF (仅本机 IP 发信)"},
        {"key": "dkim",  "rtype": "TXT","name": "dkim._domainkey", "value": dkim_txt,                                       "prio": None, "desc": "DKIM 公钥 (真实签名验签)"},
        {"key": "dmarc", "rtype": "TXT","name": "_dmarc",          "value": "v=DMARC1; p=none; rua=mailto:postmaster@%s;" % domain, "prio": None, "desc": "DMARC (p=none 观察)"},
    ]
    return records


# ---------------- DoH 验证 ---------------- #
def verify_doh(name, rtype, expect_contains=None, timeout=15):
    results = []
    for base in DOH_SERVERS:
        url = "%s?name=%s&type=%s" % (base, urllib.parse.quote(name), rtype.upper())
        headers = {"Accept": "application/dns-json"}
        code, payload = http_json(url, headers=headers, timeout=timeout)
        if code == 200 and payload.get("Status") == 0:
            values = [a.get("data", "").strip('"') for a in payload.get("Answer", []) if a.get("data")]
            if values:
                results.extend(values)
    uniq = []
    for v in results:
        if v not in uniq:
            uniq.append(v)
    return uniq


# ---------------- 主流程 ---------------- #
def main():
    ap = argparse.ArgumentParser(description="MX Direct 一键 DNS 解析 (Cloudflare)")
    ap.add_argument("--domain", required=True, help="发件域名, 如 codexses.com")
    ap.add_argument("--server-ip", required=True, help="服务器公网 IP, 如 23.94.63.137")
    ap.add_argument("--api", default="http://127.0.0.1:8088", help="MX Direct 服务器 API 地址")
    ap.add_argument("--token", required=True, help="MX Direct API Token")
    ap.add_argument("--cf-token", required=True, help="Cloudflare API Token (需 Zone Read + DNS Edit)")
    ap.add_argument("--records", default="mx,spf,dkim,dmarc", help="要发布的记录, 逗号分隔 (可选 a,mx,spf,dkim,dmarc)")
    ap.add_argument("--dry-run", action="store_true", help="只打印将要发布的记录, 不实际修改")
    ap.add_argument("--verify", action="store_true", help="发布后自动 DoH 验证生效")
    args = ap.parse_args()

    print("==> 1/4 从服务器获取 DKIM 公钥")
    code, payload = http_json(
        args.api.rstrip("/") + "/api/dkim",
        headers={"Authorization": "Bearer " + args.token},
    )
    if code != 200 or not payload.get("ok"):
        print("错误: 获取 DKIM 失败: %s" % payload)
        sys.exit(1)
    dkim_txt = payload.get("txt", "")
    record_name = payload.get("record", "")
    print("    DKIM 记录: %s" % record_name)
    print("    DKIM 公钥: %s..." % dkim_txt[:60])
    if not dkim_txt:
        print("错误: DKIM 公钥为空")
        sys.exit(1)

    want = [w.strip().lower() for w in args.records.split(",") if w.strip()]
    records = build_records(args.domain, args.server_ip, dkim_txt)
    records = [r for r in records if r["key"] in want]

    print("==> 2/4 发布 DNS 记录到 Cloudflare (%d 条)" % len(records))
    cf = Cloudflare(args.cf_token, dry_run=args.dry_run)
    if args.dry_run:
        for rec in records:
            full = args.domain if rec["name"] in ("@", "", ".") else "%s.%s" % (rec["name"], args.domain)
            val = quoted(rec["value"]) if rec["rtype"] == "TXT" else rec["value"]
            print("  [plan] %s %s -> %s  (%s)" % (rec["rtype"], full, val, rec["desc"]))
    else:
        try:
            zone = cf.zone_id(args.domain)
            print("    Zone: %s (%s)" % (args.domain, zone))
        except RuntimeError as e:
            print("错误: %s" % e)
            sys.exit(1)
        for rec in records:
            try:
                cf.upsert(args.domain, rec["rtype"], rec["name"], quoted(rec["value"]) if rec["rtype"] == "TXT" else rec["value"], rec["prio"])
            except RuntimeError as e:
                print("错误: %s %s 发布失败: %s" % (rec["rtype"], rec["name"], e))
                sys.exit(1)

    print("==> 3/4 完成")
    if args.verify and not args.dry_run:
        print("==> 4/4 等待 10 秒后验证 (DoH)")
        time.sleep(10)
        checks = [
            ("%s" % args.domain, "MX", "mail."),
            ("%s" % args.domain, "TXT", "spf"),
            ("dkim._domainkey.%s" % args.domain, "TXT", "v=dkim1"),
            ("_dmarc.%s" % args.domain, "TXT", "v=dmarc1"),
            ("mail.%s" % args.domain, "A", args.server_ip),
        ]
        for name, rtype, key in checks:
            vals = verify_doh(name, rtype)
            hit = any(key in v.lower() for v in vals)
            print("    %s %s -> %s (%s)" % (rtype, name, ", ".join(vals) or "未生效", "OK" if hit else "未找到"))
    else:
        print("==> 4/4 跳过验证 (使用 --verify 开启)")
    print("全部完成 (｡･ω･｡)ﾉ")


if __name__ == "__main__":
    main()
