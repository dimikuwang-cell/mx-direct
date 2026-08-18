#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MX Direct 图形界面发送软件
==========================
对接 mx-direct 直投服务器 (HTTP API :8088)

功能:
- 服务器地址 / Token / 连接测试 / 配置自动保存
- 发件箱随机生成 (5-7 位小写字母 @ 发件域名, 无需导入)
- 收件人导入 (TXT 每行一个邮箱)
- 主题 + 正文 (纯文本 / HTML 富文本, 可浏览器预览)
- 高级参数 (HELO域名/伪装IP/SMTP ID/by_mx/并发/间隔, 留空=服务器随机)
- 多线程批量发送 + 进度 + 实时日志 + CSV 结果

用法:
    python mx_sender_gui.py

编译 exe:
    pyinstaller --noconfirm --clean --windowed --name MXSender mx_sender_gui.py
"""
import ctypes
import json
import random
import os
import queue
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "mx_sender_gui_config.json")

CN_LAST = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳酆鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯昝管卢莫经房裘缪干解应宗丁宣贲邓郁单杭洪包诸左石崔吉钮龚程嵇邢滑裴陆荣翁荀羊於惠甄曲家封芮羿储靳汲邴糜松井段富巫乌焦巴弓牧隗山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘斜厉戎祖武符刘景詹束龙叶幸司韶郜黎蓟薄印宿白怀蒲邰从鄂索咸籍赖卓蔺屠蒙池乔阴郁胥能苍双闻莘党翟谭贡劳逄姬申扶堵冉宰郦雍却璩桑桂濮牛寿通边扈燕冀郏浦尚农温别庄晏柴瞿阎充慕连茹习宦艾鱼容向古易慎戈廖庾终暨居衡步都耿满弘匡国文寇广禄阙东欧殳沃利蔚越夔隆师巩厍聂晁勾敖融冷訾辛阚那简饶空曾毋沙乜养鞠须丰巢关蒯相查后荆红游竺权逯盖益桓公"
CN_GIVEN = "伟刚勇毅俊峰强军平保东文辉力明永健世广志义兴良海山仁波宁贵福生龙元全国胜学祥才发武新利清飞彬富顺信子杰涛昌成康星光天达安岩中茂进林有坚和彪博诚先敬震振壮会思群豪心邦承乐绍功松善厚庆磊民友裕河哲江超浩亮政谦亨奇固之轮翰朗伯宏言若鸣朋斌梁栋维启克伦翔旭鹏泽晨辰士以建家致树炎德行时泰盛雄琛钧冠策腾楠榕风航弘秀娟英华慧巧美娜静淑惠珠翠雅芝玉萍红娥玲芬芳燕彩春菊兰凤洁梅琳素云莲真环雪荣爱妹霞香月莺媛艳瑞凡佳嘉琼勤珍贞莉桂娣叶璧璐娅琦晶妍茜秋珊莎锦黛青倩婷姣婉娴瑾颖露瑶怡婵雁蓓纨仪荷丹蓉眉君琴蕊薇菁梦岚苑婕馨瑗琰韵融园艺咏卿聪澜纯毓悦昭冰爽琬茗羽希欣飘育滢馥筠柔竹霭凝晓欢霄枫芸菲寒伊亚宜可姬舒影荔枝思丽"
JP_LAST = ["佐藤","鈴木","高橋","田中","伊藤","渡辺","山本","中村","小林","加藤","吉田","山田","佐々木","山口","松本","井上","木村","林","斎藤","清水","山崎","森","池田","橋本","阿部","石川","中島","前田","藤田","小川","岡田","後藤","長谷川","村上","近藤","石井","遠藤","青木","藤井","西村","福田","太田","三浦","岡本","松田","中川","中野","原田","小野","田村","竹内","金子","和田","中山","石田","上田","森田","柴田","原","宮崎","酒井","工藤","横山","宮本","内田","高木","安藤","島田","谷口","大野","高田","丸山","今井","河野","藤原","高野","小山","武田","西田","大橋","坂本","滝口","小池","野村"]
JP_GIVEN = ["悠真","美咲","大翔","結衣","蓮","陽菜","湊","葵","凛","健太","翔太","千尋","真理子","直樹","拓海","颯太","蒼太","奏多","玲奈","愛","光","優","陽向","結愛","澪","ひかり","ゆうた","そうま","はると","さくら","ゆい","あかり","まお","りく","かいと","ゆうと","はるか","みなみ","かのん","つむぎ","いちか","こはる","みお","すず","りお","あおい","めい","ひまり","さな","もも","うた","ねね","ほのか","しおり","ゆず","あんず","つばさ","あさひ","だいち","ひびき","ゆづき","ふうか","みこと","あゆむ","はやと","きょうか","みゆき","まさる","たけし","ひろし","けんじ","よしこ","ともこ","あきら","まこと","はじめ","のぼる","おさむ","さとし","ひでお","なおこ","けいこ","じゅん","まなみ","りな","えま","みく"]
EN_FIRST = ["James","John","Robert","Michael","William","David","Richard","Joseph","Thomas","Charles","Christopher","Daniel","Matthew","Anthony","Mark","Donald","Steven","Paul","Andrew","Joshua","Kenneth","Kevin","Brian","George","Edward","Ronald","Timothy","Jason","Jeffrey","Ryan","Jacob","Gary","Nicholas","Eric","Jonathan","Stephen","Larry","Justin","Scott","Brandon","Benjamin","Samuel","Gregory","Alexander","Patrick","Frank","Raymond","Jack","Dennis","Jerry","Tyler","Aaron","Jose","Adam","Nathan","Henry","Zachary","Douglas","Peter","Kyle","Noah","Ethan","Jeremy","Walter","Christian","Keith","Roger","Terry","Austin","Sean","Gerald","Carl","Dylan","Harold","Jordan","Jesse","Bryan","Lawrence","Arthur","Gabriel","Bruce","Logan","Billy","Joe","Alan","Juan","Elijah","Willie","Albert","Wayne","Randy","Mason","Vincent","Liam","Roy","Bobby","Caleb","Bradley","Russell","Lucas","Mary","Patricia","Jennifer","Linda","Elizabeth","Barbara","Susan","Jessica","Sarah","Karen","Lisa","Nancy","Betty","Margaret","Sandra","Ashley","Kimberly","Emily","Donna","Michelle","Carol","Amanda","Dorothy","Melissa","Deborah","Stephanie","Rebecca","Sharon","Laura","Cynthia","Kathleen","Amy","Angela","Shirley","Anna","Brenda","Pamela","Emma","Nicole","Helen","Samantha","Katherine","Christine","Debra","Rachel","Carolyn","Janet","Catherine","Maria","Heather","Diane","Ruth","Julie","Olivia","Joyce","Virginia","Victoria","Kelly","Lauren","Christina","Joan","Evelyn","Judith","Megan","Cheryl","Andrea","Hannah","Jacqueline","Martha","Gloria","Teresa","Ann","Sara","Madison","Frances","Kathryn","Janice","Jean","Abigail","Alice","Julia","Judy","Sophia","Grace","Denise","Amber","Doris","Marilyn","Danielle","Beverly","Isabella","Theresa","Diana","Natalie","Brittany","Charlotte","Marie","Kayla","Alexis","Lori","Christina"]
EN_LAST = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis","Rodriguez","Martinez","Hernandez","Lopez","Gonzalez","Wilson","Anderson","Thomas","Taylor","Moore","Jackson","Martin","Lee","Perez","Thompson","White","Harris","Sanchez","Clark","Ramirez","Lewis","Robinson","Walker","Young","Allen","King","Wright","Scott","Torres","Nguyen","Hill","Flores","Green","Adams","Nelson","Baker","Hall","Rivera","Campbell","Mitchell","Carter","Roberts","Gomez","Phillips","Evans","Turner","Diaz","Parker","Cruz","Edwards","Collins","Reyes","Stewart","Morris","Morales","Murphy","Cook","Rogers","Gutierrez","Ortiz","Morgan","Cooper","Peterson","Bailey","Reed","Kelly","Howard","Ramos","Kim","Cox","Ward","Richardson","Watson","Brooks","Chavez","Wood","James","Bennett","Gray","Mendoza","Ruiz","Hughes","Price","Alvarez","Castillo","Sanders","Patel","Myers","Long","Ross","Foster","Jimenez","Powell","Jenkins","Perry","Russell","Sullivan","Bell","Coleman","Butler","Henderson","Barnes","Gonzales","Fisher","Vasquez","Simmons","Romero","Jordan","Patterson","Alexander","Hamilton","Graham","Reynolds","Griffin","Wallace","Moreno","West","Cole","Hayes","Bryant","Herrera","Gibson","Ellis","Tran","Medina","Aguilar","Stevens","Murray","Ford","Castro","Marshall","Owens","Harrison","Fernandez","Mcdonald","Woods","Washington","Kennedy","Wells","Vargas","Henry","Chen","Freeman","Webb","Tucker","Guzman","Burns","Crawford","Olson","Simpson","Porter","Hunter","Gordon","Mendez","Silva","Shaw","Snyder","Mason","Dixon","Munoz","Hunt","Hicks","Holmes","Palmer","Wagner","Black","Robertson","Boyd","Rose","Stone","Salazar","Fox","Warren","Mills","Meyer","Rice","Schmidt","Garza","Daniels","Ferguson","Nichols","Stephens","Soto","Weaver","Ryan","Gardner","Payne","Grant","Dunn","Kelley","Spencer","Hawkins","Arnold","Pierce","Vazquez","Hansen","Peters","Santos","Hart","Bradley","Knight","Elliott","Cunningham","Duncan","Armstrong","Hudson","Carroll","Lane","Riley","Andrews","Alvarado","Ray","Delgado","Berry","Perkins","Hoffman","Johnston","Matthews","Pena","Richards","Contreras","Willis","Carpenter","Lawrence","Sandoval","Guerrero","George","Chapman","Rios","Estrada","Ortega","Watkins","Greene","Nunez","Wheeler","Valdez","Larsen","Phelps","Calderon","Hale","Mack","Zimmerman","Barker","Bowman","Hodges","Powers","Schneider","Newman","Oliver","Curtis","Lucas","Luna","Burton","Maldonado","Salinas","Osborne","Bush","French","Nguyen","Kumar","Sharma","Singh","Patel"]


def random_name(mode):
    """按模式生成随机显示名: 固定/随机中文/随机日文/随机英文"""
    if mode == "随机中文":
        g = CN_GIVEN
        return random.choice(CN_LAST) + random.choice(g) + (random.choice(g) if random.random() < 0.5 else "")
    if mode == "随机日文":
        return random.choice(JP_LAST) + " " + random.choice(JP_GIVEN)
    if mode == "随机英文":
        return random.choice(EN_FIRST) + " " + random.choice(EN_LAST)
    return ""
DEFAULT_CONFIG = {
    "server": "http://23.94.63.137:8088",
    "token": "",
    "sender_domain": "codexses.com",
    "sender_count": 100,
    "subject": "",
    "body": "",
    "html": False,
    "helo_domain": "",
    "fake_ip": "",
    "smtp_id": "",
    "by_mx": "",
    "threads": 10,
    "delay": 0.0,
    "from_name": "",
    "from_name_mode": "固定",
}

UI_BG = "#f5f7fb"
UI_CARD = "#ffffff"
UI_BORDER = "#d9e2f2"
UI_TEXT = "#1f2d3d"
UI_PRIMARY = "#2f6fed"
UI_DANGER = "#e04f5f"
UI_SECONDARY = "#edf2fb"
UI_OK = "#22a06b"
UI_FONT = ("Microsoft YaHei UI", 10)
UI_FONT_B = ("Microsoft YaHei UI", 10, "bold")


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            cfg.update(loaded)
    except Exception:
        pass
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def http_json(url, headers=None, payload=None, method=None, timeout=30):
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


def load_lines_from_file(path):
    out = []
    with open(path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                out.append(line)
    return out


class MXSenderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MX Direct 发送软件")
        self.geometry("1020x780")
        self.minsize(920, 700)
        self.configure(bg=UI_BG)
        self.cfg = load_config()
        self.log_q = queue.Queue()
        self.sending = False
        self.total = 0
        self.done = 0
        self.ok_count = 0
        self.fail_count = 0
        self._adv_visible = True
        self._build_ui()
        self._load_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(120, self._drain_log)

    # ---------------- UI 构建 ----------------
    def _card(self, parent, title):
        card = tk.Frame(parent, bg=UI_CARD, highlightbackground=UI_BORDER,
                        highlightthickness=1, bd=0)
        tk.Label(card, text=title, bg=UI_CARD, fg=UI_PRIMARY,
                 font=("Microsoft YaHei UI", 11, "bold"), anchor="w").pack(
            fill="x", padx=10, pady=(8, 2))
        return card

    def _build_ui(self):
        pad = {"padx": 10, "pady": 5}
        # 顶部: 服务器配置
        top = self._card(self, "服务器配置")
        top.pack(fill="x", **pad)
        row1 = tk.Frame(top, bg=UI_CARD)
        row1.pack(fill="x", padx=10, pady=4)
        tk.Label(row1, text="API 地址", bg=UI_CARD, font=UI_FONT).pack(side="left")
        self.var_server = tk.StringVar()
        tk.Entry(row1, textvariable=self.var_server, font=UI_FONT, width=36,
                 relief="solid", bd=1).pack(side="left", padx=6)
        tk.Label(row1, text="Token", bg=UI_CARD, font=UI_FONT).pack(side="left", padx=(12, 0))
        self.var_token = tk.StringVar()
        self.ent_token = tk.Entry(row1, textvariable=self.var_token, font=UI_FONT,
                                  width=34, relief="solid", bd=1, show="*")
        self.ent_token.pack(side="left", padx=6)
        self.btn_show = tk.Button(row1, text="显示", font=UI_FONT, bg=UI_SECONDARY,
                                  relief="solid", bd=1, cursor="hand2",
                                  command=self._toggle_token)
        self.btn_show.pack(side="left", padx=2)
        self.btn_test = tk.Button(row1, text="测试连接", font=UI_FONT_B, bg=UI_PRIMARY,
                                  fg="white", relief="solid", bd=1, cursor="hand2",
                                  command=self._test_conn)
        self.btn_test.pack(side="left", padx=8)
        self.lbl_conn = tk.Label(row1, text="未测试", bg=UI_CARD, fg="gray", font=UI_FONT)
        self.lbl_conn.pack(side="left", padx=4)

        # 中部: 发件箱 / 收件人
        mid = tk.Frame(self, bg=UI_BG)
        mid.pack(fill="x", **pad)
        mid.columnconfigure(0, weight=1)
        mid.columnconfigure(1, weight=1)
        card_s = self._card(mid, "发件箱  (随机 5-7 位字母 @ 发件域名, 无需导入)")
        card_s.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        r0 = tk.Frame(card_s, bg=UI_CARD)
        r0.pack(fill="x", padx=8, pady=(6, 0))
        tk.Label(r0, text="发件域名", bg=UI_CARD, font=UI_FONT).pack(side="left")
        self.var_sender_domain = tk.StringVar()
        tk.Entry(r0, textvariable=self.var_sender_domain, font=UI_FONT, width=24,
                 relief="solid", bd=1).pack(side="left", padx=4)
        tk.Label(r0, text="数量", bg=UI_CARD, font=UI_FONT).pack(side="left", padx=(10, 0))
        self.var_sender_count = tk.StringVar()
        tk.Entry(r0, textvariable=self.var_sender_count, font=UI_FONT, width=6,
                 relief="solid", bd=1).pack(side="left", padx=4)
        self.txt_senders = tk.Text(card_s, height=7, relief="solid", bd=1,
                                   font=("Consolas", 10), bg="#fbfdff")
        self.txt_senders.pack(fill="both", expand=True, padx=8, pady=4)
        r1 = tk.Frame(card_s, bg=UI_CARD)
        r1.pack(fill="x", padx=8, pady=(0, 6))
        self.lbl_sender_cnt = tk.Label(r1, text="0 个", bg=UI_CARD, fg="gray", font=UI_FONT)
        self.lbl_sender_cnt.pack(side="left")
        tk.Button(r1, text="随机生成", font=UI_FONT, bg=UI_SECONDARY, relief="solid",
                  bd=1, cursor="hand2", command=self._gen_senders).pack(side="right", padx=2)
        tk.Button(r1, text="清空", font=UI_FONT, bg="#fdecef", fg=UI_DANGER, relief="solid",
                  bd=1, cursor="hand2", command=lambda: self._clear_text(self.txt_senders)).pack(side="right", padx=2)

        card_r = self._card(mid, "收件人  (每行一个邮箱)")
        card_r.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        self.txt_receivers = tk.Text(card_r, height=7, relief="solid", bd=1,
                                     font=("Consolas", 10), bg="#fbfdff")
        self.txt_receivers.pack(fill="both", expand=True, padx=8, pady=4)
        r2 = tk.Frame(card_r, bg=UI_CARD)
        r2.pack(fill="x", padx=8, pady=(0, 6))
        self.lbl_receiver_cnt = tk.Label(r2, text="0 个", bg=UI_CARD, fg="gray", font=UI_FONT)
        self.lbl_receiver_cnt.pack(side="left")
        tk.Button(r2, text="导入收件人", font=UI_FONT, bg=UI_SECONDARY, relief="solid",
                  bd=1, cursor="hand2", command=lambda: self._import_to(self.txt_receivers)).pack(side="right", padx=2)
        tk.Button(r2, text="清空", font=UI_FONT, bg="#fdecef", fg=UI_DANGER, relief="solid",
                  bd=1, cursor="hand2", command=lambda: self._clear_text(self.txt_receivers)).pack(side="right", padx=2)

        # 邮件内容
        card_c = self._card(self, "邮件内容")
        card_c.pack(fill="x", **pad)
        rowc = tk.Frame(card_c, bg=UI_CARD)
        rowc.pack(fill="x", padx=10, pady=4)
        rowf = tk.Frame(card_c, bg=UI_CARD)
        rowf.pack(fill="x", padx=10, pady=(0, 4))
        tk.Label(rowf, text="发件人名称", bg=UI_CARD, font=UI_FONT).pack(side="left")
        self.var_from_name = tk.StringVar()
        tk.Entry(rowf, textvariable=self.var_from_name, font=UI_FONT, width=20,
                 relief="solid", bd=1).pack(side="left", padx=6)
        tk.Label(rowf, text="随机模式", bg=UI_CARD, font=UI_FONT).pack(side="left", padx=(10, 0))
        self.var_from_mode = tk.StringVar(value="固定")
        ttk.Combobox(rowf, textvariable=self.var_from_mode, state="readonly",
                     values=["固定", "随机中文", "随机日文", "随机英文"],
                     width=10, font=UI_FONT).pack(side="left", padx=6)
        tk.Label(rowf, text="名称留空时自动使用发件箱前缀", bg=UI_CARD, fg="gray",
                 font=("Microsoft YaHei UI", 8)).pack(side="left")
        tk.Label(rowc, text="主题", bg=UI_CARD, font=UI_FONT).pack(side="left")
        self.var_subject = tk.StringVar()
        tk.Entry(rowc, textvariable=self.var_subject, font=UI_FONT, relief="solid",
                 bd=1).pack(side="left", fill="x", expand=True, padx=6)
        self.var_html = tk.BooleanVar(value=bool(self.cfg.get("html")))
        tk.Radiobutton(rowc, text="纯文本", variable=self.var_html, value=False,
                       bg=UI_CARD, font=UI_FONT).pack(side="left", padx=2)
        tk.Radiobutton(rowc, text="HTML", variable=self.var_html, value=True,
                       bg=UI_CARD, font=UI_FONT).pack(side="left", padx=2)
        tk.Button(rowc, text="预览", font=UI_FONT, bg=UI_SECONDARY, relief="solid",
                  bd=1, cursor="hand2", command=self._preview).pack(side="left", padx=6)
        self.txt_body = tk.Text(card_c, height=8, relief="solid", bd=1,
                                font=("Microsoft YaHei UI", 10), bg="#fbfdff",
                                wrap="word")
        self.txt_body.pack(fill="x", padx=8, pady=4)

        # 高级参数
        self.card_adv = self._card(self, "高级参数  (留空 = 服务器自动随机)")
        self.card_adv.pack(fill="x", **pad)
        av = tk.Frame(self.card_adv, bg=UI_CARD)
        av.pack(fill="x", padx=10, pady=4)
        self.var_helo = tk.StringVar()
        self.var_ip = tk.StringVar()
        self.var_smtp = tk.StringVar()
        self.var_bymx = tk.StringVar()
        self.var_threads = tk.StringVar(value=str(self.cfg.get("threads", 10)))
        self.var_delay = tk.StringVar(value=str(self.cfg.get("delay", 0.0)))
        def lbl_entry(parent, text, var, width=18, row=0, col=0, extra=""):
            f = tk.Frame(parent, bg=UI_CARD)
            f.grid(row=row, column=col, sticky="w", padx=(0, 14), pady=2)
            tk.Label(f, text=text, bg=UI_CARD, font=UI_FONT).pack(side="left")
            tk.Entry(f, textvariable=var, font=UI_FONT, width=width, relief="solid",
                     bd=1).pack(side="left", padx=4)
            if extra:
                tk.Label(f, text=extra, bg=UI_CARD, fg="gray", font=("Microsoft YaHei UI", 8)).pack(side="left")
            return f
        lbl_entry(av, "HELO 域名", self.var_helo, 16, 0, 0)
        lbl_entry(av, "伪装 IP", self.var_ip, 14, 0, 1)
        lbl_entry(av, "SMTP ID", self.var_smtp, 10, 0, 2)
        lbl_entry(av, "by MX", self.var_bymx, 16, 1, 0, "默认自动查收件人MX")
        lbl_entry(av, "并发线程", self.var_threads, 6, 1, 1)
        lbl_entry(av, "间隔秒", self.var_delay, 6, 1, 2)

        # 底部: 发送 + 进度 + 日志
        bottom = tk.Frame(self, bg=UI_BG)
        bottom.pack(fill="both", expand=True, **pad)
        rowb = tk.Frame(bottom, bg=UI_BG)
        rowb.pack(fill="x")
        self.btn_send = tk.Button(rowb, text="开始发送", font=("Microsoft YaHei UI", 13, "bold"),
                                  bg=UI_PRIMARY, fg="white", relief="solid", bd=1,
                                  cursor="hand2", padx=24, pady=6, command=self._start_send)
        self.btn_send.pack(side="left")
        self.btn_stop = tk.Button(rowb, text="停止", font=UI_FONT_B, bg="#fdecef",
                                  fg=UI_DANGER, relief="solid", bd=1, cursor="hand2",
                                  state="disabled", command=self._stop_send)
        self.btn_stop.pack(side="left", padx=8)
        self.progress = ttk.Progressbar(rowb, length=300, mode="determinate")
        self.progress.pack(side="left", padx=10)
        self.lbl_stat = tk.Label(rowb, text="就绪", bg=UI_BG, fg=UI_TEXT, font=UI_FONT_B)
        self.lbl_stat.pack(side="left", padx=6)
        self.txt_log = scrolledtext.ScrolledText(bottom, height=7, relief="solid",
                                                 bd=1, state="disabled", wrap="word",
                                                 font=("Consolas", 9))
        self.txt_log.pack(fill="both", expand=True, pady=(8, 0))
        self.log("就绪: 填写服务器/Token/内容后点击 开始发送")

    # ---------------- 工具 ----------------
    def log(self, msg, color=None):
        self.txt_log.configure(state="normal")
        if color:
            self.txt_log.tag_config("c", foreground=color)
            self.txt_log.insert("end", msg + "\n", "c")
        else:
            self.txt_log.insert("end", msg + "\n")
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    def _drain_log(self):
        try:
            while True:
                item = self.log_q.get_nowait()
                self.log(*item)
        except queue.Empty:
            pass
        self.after(150, self._drain_log)

    def _toggle_token(self):
        self.ent_token.configure(show="" if self.ent_token.cget("show") else "*")

    def _clear_text(self, w):
        w.delete("1.0", "end")
        self._update_cnt()

    def _import_to(self, w):
        path = filedialog.askopenfilename(title="选择 TXT 文件",
                                          filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            lines = load_lines_from_file(path)
        except Exception as e:
            messagebox.showerror("导入失败", str(e))
            return
        w.insert("end", "\n".join(lines) + "\n")
        self._update_cnt()
        self.log("已导入 %d 行: %s" % (len(lines), os.path.basename(path)))

    def _gen_senders(self, auto=False):
        domain = self.var_sender_domain.get().strip().lstrip("@")
        if not domain:
            if auto:
                return
            messagebox.showwarning("提示", "请先填写发件域名")
            return
        try:
            count = max(1, int(self.var_sender_count.get() or 100))
        except ValueError:
            count = 100
        seen = set()
        out = []
        while len(out) < count:
            n = random.randint(5, 7)
            addr = "".join(random.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(n))
            if addr in seen:
                continue
            seen.add(addr)
            out.append(addr + "@" + domain)
        self.txt_senders.delete("1.0", "end")
        self.txt_senders.insert("1.0", "\n".join(out) + "\n")
        self._update_cnt()
        self.log("%s生成 %d 个随机发件箱: 5-7位字母@%s" % ("自动" if auto else "已", count, domain))

    def _update_cnt(self):
        s = self._parse_senders()
        r = self._parse_receivers()
        self.lbl_sender_cnt.configure(text="%d 个" % len(s))
        self.lbl_receiver_cnt.configure(text="%d 个" % len(r))
        return s, r

    def _parse_senders(self):
        out = []
        for line in self.txt_senders.get("1.0", "end").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            email = parts[0]
            if "@" not in email:
                continue
            out.append({"email": email,
                        "helo": parts[1] if len(parts) > 1 else "",
                        "ip": parts[2] if len(parts) > 2 else ""})
        return out

    def _parse_receivers(self):
        out = []
        for line in self.txt_receivers.get("1.0", "end").splitlines():
            line = line.strip()
            if line and "@" in line and not line.startswith("#"):
                out.append(line)
        return out

    def _gather_cfg(self):
        cfg = {
            "server": self.var_server.get().strip(),
            "token": self.var_token.get().strip(),
            "subject": self.var_subject.get().strip(),
            "body": self.txt_body.get("1.0", "end-1c"),
            "html": bool(self.var_html.get()),
            "from_name": self.var_from_name.get().strip(),
            "from_name_mode": self.var_from_mode.get() or "固定",
            "helo_domain": self.var_helo.get().strip(),
            "fake_ip": self.var_ip.get().strip(),
            "smtp_id": self.var_smtp.get().strip(),
            "by_mx": self.var_bymx.get().strip(),
            "threads": int(self.var_threads.get() or 10),
            "delay": float(self.var_delay.get() or 0),
            "sender_domain": self.var_sender_domain.get().strip().lstrip("@"),
            "sender_count": int(self.var_sender_count.get() or 100),
        }
        return cfg

    def _save_cfg(self):
        self.cfg.update(self._gather_cfg())
        save_config(self.cfg)

    def _load_ui(self):
        c = self.cfg
        self.var_server.set(c.get("server", ""))
        self.var_token.set(c.get("token", ""))
        self.var_subject.set(c.get("subject", ""))
        self.txt_body.insert("1.0", c.get("body", ""))
        self.var_html.set(bool(c.get("html")))
        self.var_from_name.set(c.get("from_name", ""))
        self.var_from_mode.set(c.get("from_name_mode", "固定"))
        self.var_helo.set(c.get("helo_domain", ""))
        self.var_ip.set(c.get("fake_ip", ""))
        self.var_smtp.set(c.get("smtp_id", ""))
        self.var_bymx.set(c.get("by_mx", ""))
        self.var_threads.set(str(c.get("threads", 10)))
        self.var_delay.set(str(c.get("delay", 0)))
        self.var_sender_domain.set(c.get("sender_domain", "codexses.com"))
        self.var_sender_count.set(str(c.get("sender_count", 100)))
        self._update_cnt()
        if not self._parse_senders():
            self._gen_senders(auto=True)

    def _on_close(self):
        self._save_cfg()
        self.destroy()

    # ---------------- 动作 ----------------
    def _test_conn(self):
        server = self.var_server.get().strip().rstrip("/")
        token = self.var_token.get().strip()
        if not server:
            messagebox.showwarning("提示", "请先填写 API 地址")
            return
        self.lbl_conn.configure(text="测试中...", fg="orange")
        def work():
            code, payload = http_json(server + "/health", timeout=10)
            return code, payload
        def done(code, payload):
            if code == 200 and payload.get("ok"):
                self.lbl_conn.configure(text="连接正常 (%s)" % payload.get("service", "?"), fg=UI_OK)
            else:
                self.lbl_conn.configure(text="连接失败 (%s)" % code, fg=UI_DANGER)
        threading.Thread(target=lambda: self.after(0, lambda r=work(): done(*r)),
                         daemon=True).start()

    def _preview(self):
        body = self.txt_body.get("1.0", "end-1c")
        subject = self.var_subject.get().strip() or "预览"
        html = body if self.var_html.get() else "<pre>%s</pre>" % body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        tmp = os.path.join(BASE_DIR, "_preview.html")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("<!DOCTYPE html><html><head><meta charset='utf-8'><title>%s</title></head><body>%s</body></html>" % (subject, html))
        webbrowser.open("file:///" + tmp.replace("\\", "/"))

    def _start_send(self):
        if self.sending:
            return
        cfg = self._gather_cfg()
        self._save_cfg()
        if not cfg["server"] or not cfg["token"]:
            messagebox.showwarning("提示", "请填写 API 地址 和 Token")
            return
        senders = self._parse_senders()
        receivers = self._parse_receivers()
        if not senders:
            messagebox.showwarning("提示", "发件箱为空")
            return
        if not receivers:
            messagebox.showwarning("提示", "收件人为空")
            return
        if not cfg["subject"] and not cfg["body"]:
            messagebox.showwarning("提示", "主题和正文都是空的, 确认要发吗?", parent=self)
        self.sending = True
        self.btn_send.configure(state="disabled", text="发送中...")
        self.btn_stop.configure(state="normal")
        self.total = len(receivers)
        self.done = 0
        self.ok_count = 0
        self.fail_count = 0
        self.progress.configure(maximum=max(self.total, 1), value=0)
        self.lbl_stat.configure(text="0/%d" % self.total)
        self.log("==== 开始发送: 发件箱 %d 个, 收件人 %d 个, 线程 %d ====" %
                 (len(senders), len(receivers), cfg["threads"]))
        threading.Thread(target=self._worker_main, args=(cfg, senders, receivers),
                         daemon=True).start()

    def _worker_main(self, cfg, senders, receivers):
        results = []
        def call_one(i, to):
            sender = senders[i % len(senders)]
            if cfg["delay"] > 0:
                time.sleep(cfg["delay"])
            fname = random_name(cfg.get("from_name_mode", "固定"))
            if not fname:
                fname = cfg.get("from_name", "") or sender["email"].split("@")[0]
            payload = {
                "to": to,
                "from_addr": sender["email"],
                "from_name": fname,
                "subject": cfg["subject"],
                "body": cfg["body"],
                "html": cfg["html"],
                "helo_domain": cfg["helo_domain"],
                "fake_ip": cfg["fake_ip"],
                "smtp_id": cfg["smtp_id"],
                "by_mx": cfg["by_mx"],
            }
            code, resp = http_json(cfg["server"].rstrip("/") + "/api/send", payload=payload,
                              headers={"Authorization": "Bearer " + cfg["token"]}, timeout=60)
            ok = bool(resp.get("ok"))
            info = resp.get("error") or resp.get("mx") or ""
            return ok, to, sender["email"], info
        try:
            with ThreadPoolExecutor(max_workers=max(1, cfg["threads"])) as ex:
                futs = [ex.submit(call_one, i, to) for i, to in enumerate(receivers)]
                for fut in as_completed(futs):
                    ok, to, frm, info = fut.result()
                    self.done += 1
                    if ok:
                        self.ok_count += 1
                    else:
                        self.fail_count += 1
                    results.append("%s,%s,%s,%s,%s" % (
                        time.strftime("%Y-%m-%d %H:%M:%S"), to, frm,
                        "OK" if ok else "FAIL", info.replace(",", " ")))
                    self.log_q.put(("[OK ] %s -> %s  (%s)" % (frm, to, info) if ok else
                                    "[FAIL] %s -> %s  (%s)" % (frm, to, info),
                                    UI_OK if ok else UI_DANGER))
                    self.after(0, self._update_progress)
        except Exception as e:
            self.log_q.put(("发送线程异常: %s" % e, UI_DANGER))
        finally:
            csv_path = os.path.join(BASE_DIR, "发送结果_%s.csv" % time.strftime("%Y%m%d_%H%M%S"))
            try:
                with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
                    f.write("时间,收件人,发件人,状态,详情\n" + "\n".join(results))
            except Exception:
                csv_path = ""
            self.after(0, lambda: self._finish(csv_path))

    def _update_progress(self):
        self.progress.configure(value=self.done)
        self.lbl_stat.configure(text="%d/%d  成功%d 失败%d" % (self.done, self.total, self.ok_count, self.fail_count))

    def _finish(self, csv_path):
        self.sending = False
        self.btn_send.configure(state="normal", text="开始发送")
        self.btn_stop.configure(state="disabled")
        self.lbl_stat.configure(text="完成: 成功 %d / 失败 %d / 共 %d" % (self.ok_count, self.fail_count, self.total))
        msg = "发送完成: 成功 %d, 失败 %d" % (self.ok_count, self.fail_count)
        if csv_path:
            msg += "\n结果已保存: %s" % csv_path
        messagebox.showinfo("发送完成", msg)
        self.log("==== 发送完成: 成功 %d, 失败 %d, 结果: %s ====" % (self.ok_count, self.fail_count, csv_path or "无"))

    def _stop_send(self):
        # 简单处理: 置空剩余任务由线程自然结束; 这里仅提示
        self.log("提示: 已在发送的任务会继续完成, 新任务不再提交 (当前实现为整批, 请等待完成或关闭窗口)", UI_DANGER)


if __name__ == "__main__":
    app = MXSenderApp()
    app.mainloop()
