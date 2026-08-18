# -*- coding: utf-8 -*-
import sys, os, json
sys.path.insert(0, "I:/codex1/mx_direct")
import mx_direct_server as m

req = {
    "to": "1767640870@qq.com",
    "from_addr": "sender@codexses.com",
    "from_name": "AC Test",
    "subject": "头生成验证",
    "body": "测试正文第二行",
    "helo_domain": "mail.rand-2026.xzses.com",
    "fake_ip": "8.8.8.8",
    "smtp_id": "240F6BB",
}
msg, helo, ip, sid, by_mx = m.build_message(req)
print("HELO:", helo)
print("BY_MX:", by_mx)
print("========== 邮件全文 ==========")
print(msg)
print("========== END ==========")
