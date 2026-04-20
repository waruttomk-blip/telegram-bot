# ============================================================
#  🤖 Telegram Order Bot v6
#  แก้ไข v6:
#   - detect_shop อ่าน "เพจ" และ "ร้าน" ได้ทั้งคู่
#   - ของแถมหลายบรรทัด: parse บรรทัดที่ต่อเนื่องหลัง "แถม" แรกด้วย
#   - font fallback: ถ้าตัวอักษรแสดงผิด ลองใช้ system font
#   - keyword order: levoit/aircare_lab ตรวจก่อน aircare เสมอ
# ============================================================

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from PIL import Image, ImageDraw, ImageFont
import os

TOKEN = os.getenv("TOKEN")
FONT_SIZE      = 32
FONT_SIZE_INFO = 30

# ============================================================
# 🔤 Font loader — หา font ที่ใช้ได้จริง
# ============================================================

def load_font(size):
    candidates = [
        "THSarabunNew.ttf",
        "THSarabunNew Bold.ttf",
        "/usr/share/fonts/truetype/thai/TlwgTypist.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf",
        "C:/Windows/Fonts/tahoma.ttf",
        "C:/Windows/Fonts/cordia.ttf",
        "C:/Windows/Fonts/THSarabunNew.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except:
                continue
    return ImageFont.load_default()

# ============================================================
# 🛠️ Utility
# ============================================================

def split_val(line):
    for sep in [" : ", ": ", " :"]:
        if sep in line:
            return line.split(sep, 1)[-1].strip()
    # ถ้าไม่มี separator ลองตัดส่วน label ออก
    for kw in ["สินค้า","ชื่อผู้รับ","ที่อยู่จัดส่ง","เบอร์โทร","จำนวน",
               "ยอดโอนชำระ","ยอดโอน","เก็บปลายทาง"]:
        if line.startswith(kw):
            return line[len(kw):].strip()
    return line.strip()

def digits(text):
    return re.sub(r"[^\d]", "", str(text)) or "0"

def is_field(line):
    fields = ["เบอร์","โทร","สินค้า","ยอด","จำนวน","ไซส์","น้ำหนัก",
              "แถม","เก็บ","ร้าน","เพจ","เฟส","เลข","วันที่","ชื่อ"]
    return any(k in line for k in fields)

def is_address(line):
    kws = ["หมู่","ถนน","ซอย","ต.","อ.","จ.","แขวง","เขต","กทม","ก.ท.ม",
           "กรุงเทพ","ชั้น","ห้อง","อาคาร","ตำบล","อำเภอ","จังหวัด","หมู่บ้าน",
           "โรงแรม","คอนโด","แฟลต","หมู่ที่","บจก","บริษัท","มหาวิทยาลัย",
           "โรงเรียน","ลาดกระบัง","บางกะปิ","ลาดพร้าว","สาทร","สุขุมวิท",
           "รามคำแหง","พระราม","นิคม","ปากทาง","ไพรสณฑ์","ราชาเทวะ"]
    return any(k in line for k in kws)

def fmt(value, dash=False):
    try:
        n = int(str(value).replace(",","").replace(".","").replace("-","") or "0")
        return f"{n:,}.-" if dash else f"{n:,}.00"
    except:
        return "0.00"

def put(draw, text, pos, font, line_h=44, color="black"):
    if not text:
        return
    draw.text((pos[0], pos[1]), str(text), font=font, fill=color)

def put_center(draw, text, pos, font, col_width, color="black"):
    if not text:
        return
    text = str(text)
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
    except:
        tw = len(text) * (font.size // 2)
    x = pos[0] + max(0, (col_width - tw) // 2)
    draw.text((x, pos[1]), text, font=font, fill=color)

M_TH = ["","มกราคม","กุมภาพันธ์","มีนาคม","เมษายน","พฤษภาคม","มิถุนายน",
         "กรกฎาคม","สิงหาคม","กันยายน","ตุลาคม","พฤศจิกายน","ธันวาคม"]

def thai_date():
    n = datetime.datetime.now()
    return f"{n.day} {M_TH[n.month]} {n.year + 543}"

# ============================================================
# 📌 CONFIG ร้าน
# ============================================================

_AC_POS = {
    "name":       (420, 168),
    "address":    (380, 233),
    "phone":      (365, 298),
    "order_no":   (1847, 198),
    "date":       (1847, 279),
    "row1_code":  (100,  525), "row1_item":  (660,  525),
    "row1_qty":   (1380, 525), "row1_price": (1830, 525),
    "row2_code":  (100,  645), "row2_item":  (660,  645),
    "row2_qty":   (1380, 645), "row2_price": (1830, 645),
    "row3_item":  (660,  750), "row3_qty":   (1380, 750),
    "total":      (1870, 850), "cod":        (1870, 975),
    "transfer":   (1870, 1080),
}

_AC_PRODUCTS = {
    "air purifier 4 lite":    ("AC00001", "Xiaomi Air Purifier 4 Lite"),
    "air purifier 4 compact": ("AC00002", "Xiaomi Smart Air Purifier 4 Compact"),
    "air purifier 4":         ("AC00003", "Xiaomi Smart Air Purifier 4"),
    "air purifier 3c":        ("AC00004", "Xiaomi Mi Air Purifier 3C"),
    "air purifier 3h":        ("AC00005", "Xiaomi Mi Air Purifier 3H"),
    "core 600s":              ("AC00013", "Levoit รุ่น Core 600S"),
    "core 400s":              ("AC00010", "Levoit รุ่น Core 400S"),
    "core 300s":              ("AC00011", "Levoit รุ่น Core 300S"),
    "core 200s":              ("AC00012", "Levoit รุ่น Core 200S"),
    "Vital 100S":                 ("AC00010", "Levoit Vital 100S"),
}

SHOPS = {
    "aircare": {
        "template": "template_aircare.jpg",
        "display_name": "Air Clean Smarter Living",
        "pos": _AC_POS, "fixed": {"order_no": "AC18195345TH"},
        "product_codes": _AC_PRODUCTS,
    },
    "aircare_lab": {
        "template": "template_aircare_lab.jpg",
        "display_name": "AirCare Lab Home Air Solutions",
        "pos": _AC_POS, "fixed": {"order_no": "AC18195345TH"},
        "product_codes": _AC_PRODUCTS,
    },
    "levoit": {
        "template": "template_levoit.jpg",
        "display_name": "Air purifiers and electrical",
        "pos": _AC_POS, "fixed": {"order_no": "AC18195345TH"},
        "product_codes": _AC_PRODUCTS,
    },
    "gold": {
        "template": "template_gold.jpg",
        "display_name": "Gold & Jewelry",
        "pos": {
            "name":(205,195),"address":(283,260),"phone":(265,330),
            "track_no":(1975,174),"order_no":(1900,220),"date":(1890,263),
            "row1_no":(115,525),"row1_code":(380,525),"row1_item":(685,525),
            "row1_qty":(1490,525),"row1_total":(1870,525),
            "row2_no":(115,625),"row2_code":(380,625),"row2_item":(690,625),
            "row2_qty":(1490,625),"row2_total":(1870,625),
            "row3_no":(115,745),"row3_code":(380,745),"row3_item":(690,745),
            "row3_qty":(1490,745),"row3_total":(1870,745),
            "row4_no":(115,865),"row4_code":(380,865),"row4_item":(690,865),
            "row4_qty":(1490,865),"row4_total":(1870,865),
            "grand_total":(2060,895),"discount":(1960,965),
            "vat":(1950,1035),"net_total":(1930,1105),
        },
        "fixed": {"track_no":"GJS220307000131","order_no":"GJ-211212001",
                  "discount":"0.00","vat":"0.00"},
        "product_codes": {
            "แหวน":("GJ000001","แหวนทองแท้ 96.5% หนัก 1 กรัม","วง"),
            "สร้อยคอ":("GJ000002","สร้อยคอทองแท้ 96.5% หนัก 1 กรัม","เส้น"),
            "สร้อยข้อมือ":("GJ000003","สร้อยข้อมือทองแท้ 96.5% หนัก 1 กรัม","เส้น"),
            "กำไล":("GJ000004","กำไลทองแท้ 96.5% หนัก 1 กรัม","วง"),
            "ต่างหู":("GJ000005","ต่างหูทองแท้ 96.5% หนัก 1 กรัม","คู่"),
            "ทองแผ่น":("GJ000006","ทองแผ่นทองแท้ 96.5% หนัก 1 กรัม","ชิ้น"),
        },
    },
}

# ============================================================
# 🔍 detect_shop
# ชื่อร้านอาจมาใน "ร้าน.", "ร้าน :", "เพจ ", "เพจ." ฯลฯ
# ============================================================

# ลำดับสำคัญ: specific → general
_SHOP_NAME_MAP = [
    ("aircare lab home air solutions", "aircare_lab"),
    ("aircare lab",                    "aircare_lab"),
    ("air purifiers and electrical",   "levoit"),
    ("air purifier and electrical",    "levoit"),
    ("air clean smarter living",       "aircare"),
    ("aircare thailand",               "aircare"),
    ("gold & jewelry",                 "gold"),
    ("gold and jewelry",               "gold"),
]

_SHOP_KW = {
    "levoit":      ["levoit","core 400s","core 300s","core 200s","core 600s",
                    "air purifiers and electrical","air purifier and electrical"],
    "aircare_lab": ["aircare lab home","aircare lab"],
    "aircare":     ["air clean smarter","aircare thailand","aircare"],
    "gold":        ["gold & jewelry","gold and jewelry","แหวนทอง","สร้อยคอทอง",
                    "กำไลทอง","ทองแท้","96.5","ทองแผ่น"],
}

def detect_shop(text):
    # 1) ตรวจทุกบรรทัดที่มี "ร้าน" หรือ "เพจ"
    for line in text.split("\n"):
        lo = line.lower().strip()
        if not any(k in lo for k in ["ร้าน","เพจ"]):
            continue
        # ตัด label ออก แล้วเอาค่าที่เหลือ
        val = re.split(r"(ร้าน|เพจ)\.?\s*:?\s*", lo)[-1].strip()
        # ลบ trailing garbage เช่น "ไม่ได้แจ้งที่อยู่"
        val = val.split("ไม่")[0].strip()
        for name, key in _SHOP_NAME_MAP:
            if name in val:
                return key

    # 2) keyword fallback ทั้งข้อความ
    t = text.lower()
    for key in ["levoit","aircare_lab","aircare","gold"]:
        if any(kw in t for kw in _SHOP_KW[key]):
            return key

    # 3) ถ้ามี xiaomi / air purifier ทั่วไป → aircare
    if any(k in t for k in ["xiaomi","air purifier","เครื่องฟอก"]):
        return "aircare"

    return None

# ============================================================
# 📋 Parse ออเดอร์
# ============================================================

def parse_order(text):
    data = {
        "name":"","address_lines":[],"phone":"",
        "transfer":"0","cod":"0",
        "freebies":[],"products":[],"n_machines":0,
    }
    lines       = [l.strip() for l in text.split("\n") if l.strip()]
    cur_prod    = {}
    found_addr  = False
    in_freebie  = False   # ← flag: กำลังอ่านบรรทัดของแถมต่อเนื่อง

    for line in lines:
        lo = line.lower()

        # ---- ชื่อผู้รับ ----
        if any(k in line for k in ["ชื่อผู้รับ","ชื่อผู้รับสิทธิ์","ชื่อ :"]):
            in_freebie = False
            raw = split_val(line)
            data["name"] = "คุณ " + re.sub(r"^คุณ\s*","",raw).strip()

        # ---- ที่อยู่ ----
        elif any(k in line for k in ["ที่อยู่จัดส่ง","ที่อยู่จัด","ที่อยู่ :"]):
            in_freebie = False; found_addr = True
            val = split_val(line)
            if val: data["address_lines"].append(val)

        elif found_addr and is_address(line) and not is_field(line):
            data["address_lines"].append(line)

        # ---- เบอร์โทร ----
        elif any(k in line for k in ["เบอร์โทร","เบอรโทร","เบอร์ :","โทร :"]):
            found_addr = False; in_freebie = False
            data["phone"] = split_val(line)

        # ---- สินค้า ----
        elif any(k in line for k in ["สินค้า :","สินค้าที่รับสิทธิ์","สินค้าที่รับ","สินค้า:"]):
            in_freebie = False
            if cur_prod: data["products"].append(cur_prod)
            cur_prod = {"name":split_val(line),"qty":"1","size":"","unit":""}

        # ---- ไซส์ ----
        elif "ไซส์" in line and cur_prod:
            val = split_val(line)
            if "/" in val:
                parts = val.split("/")
                cur_prod["size"] = parts[0].strip()
                m = re.match(r"(\d+)\s*(.*)", parts[1].strip())
                if m:
                    cur_prod["qty"] = m.group(1)
                    cur_prod["unit"] = m.group(2).strip()
            else:
                cur_prod["size"] = val

        # ---- น้ำหนัก ----
        elif "น้ำหนัก" in line and cur_prod:
            cur_prod["weight"] = split_val(line)

        # ---- จำนวน ----
        elif "จำนวน" in line and "ของแถม" not in lo:
            in_freebie = False
            m = re.search(r"จำนวน\s*:?\s*(\d+)\s*(.*)", line)
            if m:
                data["n_machines"] = int(m.group(1))
                if cur_prod:
                    cur_prod["qty"] = m.group(1)
                    unit = re.sub(r"เครื่อง","",m.group(2)).strip()
                    if unit: cur_prod["unit"] = unit
            elif cur_prod:
                cur_prod["qty"] = digits(split_val(line))

        # ---- ยอดโอน ----
        elif any(k in line for k in ["ยอดโอนชำระ","ยอดโอน"]):
            in_freebie = False
            data["transfer"] = digits(split_val(line))

        # ---- ปลายทาง / COD ----
        elif any(k in line for k in ["เก็บปลายทาง","ชำระปลายทาง","เก็บปลาย"]):
            in_freebie = False
            data["cod"] = digits(split_val(line))

        # ---- ของแถม (บรรทัดที่มี keyword แถม / emoji) ----
        elif any(k in lo for k in ["แถม","🚀","🎁"]) and \
             not any(k in lo for k in ["ร้าน","เพจ","เฟส","ยอด","สินค้า"]):
            in_freebie = True
            _parse_freebie_line(line, data)

        # ---- บรรทัดต่อเนื่องของแถม (ไม่มี keyword แต่มาหลัง "แถม") ----
        elif in_freebie and _looks_like_freebie(line):
            _parse_freebie_line(line, data)

        else:
            # บรรทัดที่เป็น field อื่นๆ → หยุด freebie mode
            if is_field(line):
                in_freebie = False

    if cur_prod: data["products"].append(cur_prod)
    data["address"] = " ".join(data["address_lines"])
    return data


def _looks_like_freebie(line):
    """บรรทัดที่น่าจะเป็นของแถมต่อเนื่อง:
       มีตัวเลข + หน่วย หรือมี emoji หรือขึ้นต้นด้วย 🚀
    """
    lo = line.lower()
    # ถ้าเป็น field อื่น → ไม่ใช่
    if any(k in lo for k in ["ร้าน","เพจ","เฟส","เบอร์","ชื่อ","ที่อยู่","ยอด"]):
        return False
    # มี emoji หรือมีตัวเลข+หน่วย
    has_unit = bool(re.search(r"\d+\s*(ชิ้น|อัน|ตัว|วง|เส้น|กล่อง|เครื่อง)", lo))
    has_emoji = bool(re.search(r"[\U0001F300-\U0001FFFF\U00002600-\U000027FF]", line))
    return has_unit or has_emoji


def _parse_freebie_line(line, data):
    # ลบ emoji ทั้งหมด
    raw = re.sub(r"[\U0001F300-\U0001FFFF\U00002600-\U000027FF\U00002702-\U000027B0]",
                 "", line).strip()

    # ลบ prefix พวกนี้ออก
    raw = re.sub(r"^(ของแถม|📌แถมฟรี|📌แถม|📌|แถมฟรี|แถม|ฟรี)\s*",
                 "", raw, flags=re.IGNORECASE).strip(" :：")

    if not raw:
        return

    parts = [p.strip() for p in re.split(r"[,，]", raw) if p.strip()]

    for part in parts:
        m = re.search(r"(\d+)\s*(ชิ้น|อัน|เส้น|วง|กล่อง|ถุง|ซอง|ตัว|เครื่อง)", part)
        if m:
            qty_str  = m.group(0).strip()
            name_str = part[:m.start()].strip()
        else:
            qty_str  = ""
            name_str = part.strip()

        if name_str:
            data["freebies"].append({
                "name": name_str,
                "qty": qty_str
            })


# ============================================================
# 🔎 Product lookup
# ============================================================

def lookup_product(pname, pc, default_code="AC00001"):
    plo = pname.lower()
    for key, val in pc.items():
        if key.lower() in plo:
            return val[0], val[1]
    return default_code, pname

def lookup_gold(pname, pc):
    plo = pname.lower()
    for key, val in pc.items():
        if key.lower() in plo:
            return val
    return ("GJ000001", pname, "ชิ้น")

# ============================================================
# 🖼️ Builder: AirCare (ใช้ร่วมกัน 3 ร้าน)
# ============================================================

def make_aircare(data, shop):
    img  = Image.open(shop["template"]).convert("RGB")
    draw = ImageDraw.Draw(img)
    font      = load_font(FONT_SIZE)
    font_info = load_font(FONT_SIZE_INFO)
    p    = shop["pos"]
    fix  = shop["fixed"]
    pc   = shop["product_codes"]

    transfer = int(data["transfer"])
    cod      = int(data["cod"])
    total    = transfer + cod
    products = data["products"] or [{"name":"Xiaomi Air Purifier 4 Compact","qty":"1"}]
    freebies = data["freebies"]

    # n_machines: ใช้ค่าที่ parse ได้ ถ้า 0 ใช้ qty ของสินค้าแรก
    n_machines = data.get("n_machines") or int(products[0].get("qty","1"))
    if n_machines == 0: n_machines = 1

    col_w = {
        "code":  p["row1_item"][0]  - p["row1_code"][0],
        "item":  p["row1_qty"][0]   - p["row1_item"][0],
        "qty":   p["row1_price"][0] - p["row1_qty"][0],
        "price": 260,
    }

    # ลูกค้า
    put(draw, data["name"],    p["name"],    font_info)
    put(draw, data["address"], p["address"], font_info)
    put(draw, data["phone"],   p["phone"],   font_info)

    # เลขที่/วันที่
    put(draw, fix["order_no"], p["order_no"], font)
    put(draw, thai_date(),     p["date"],     font)

    # แถว 1: สินค้าหลัก
    prod = products[0]
    code, full_name = lookup_product(prod["name"], pc)
    put_center(draw, code,                    p["row1_code"],  font, col_w["code"])
    put_center(draw, full_name,               p["row1_item"],  font, col_w["item"])
    put_center(draw, f"{n_machines} เครื่อง", p["row1_qty"],   font, col_w["qty"])
    put_center(draw, fmt(total, dash=True),   p["row1_price"], font, col_w["price"])

    next_row = 2
    # แถว 2: สินค้าที่ 2 (ถ้ามี)
    if len(products) > 1:
        p2 = products[1]
        c2, fn2 = lookup_product(p2["name"], pc)
        q2 = p2.get("qty","1")
        put_center(draw, c2,               p["row2_code"],  font, col_w["code"])
        put_center(draw, fn2,              p["row2_item"],  font, col_w["item"])
        put_center(draw, f"{q2} เครื่อง", p["row2_qty"],   font, col_w["qty"])
        put_center(draw, "-",              p["row2_price"], font, col_w["price"])
        next_row = 3

    # ของแถม: ขึ้นแถวถัดจากสินค้าสุดท้าย + นำหน้า "แถมฟรี "
    if not freebies:
        freebies = [{"name":"ไส้กรอง Xiaomi MI Air Purifier","qty":f"{4*n_machines} ชิ้น"}]

    for idx, fb in enumerate(freebies):
        rn = next_row + idx
        if rn > 3: break
        ik = f"row{rn}_item"
        qk = f"row{rn}_qty"
        if ik not in p: break

        fb_name = fb["name"].strip() or "ของแถม"

        # ลบคำว่า แถม/แถมฟรี/ฟรี ทุกตำแหน่ง ไม่ใช่แค่ข้างหน้า
        fb_name = re.sub(r"(แถมฟรี|แถม|ฟรี)", "", fb_name)

        # ลบช่องว่างซ้ำ
        fb_name = re.sub(r"\s+", " ", fb_name).strip()
        
        fb_name = "แถมฟรี " + fb_name
        fb_qty = fb["qty"].strip() if fb.get("qty") else ""

        put_center(draw, fb_name, p[ik], font, col_w["item"])
        if fb_qty and qk in p:
            put_center(draw, fb_qty, p[qk], font, col_w["qty"])

    put(draw, fmt(total),    p["total"],    font)
    put(draw, fmt(cod),      p["cod"],      font)
    put(draw, fmt(transfer), p["transfer"], font)
    return img

# ============================================================
# 🖼️ Builder: Gold & Jewelry
# ============================================================

def make_gold(data, shop):
    img  = Image.open(shop["template"]).convert("RGB")
    draw = ImageDraw.Draw(img)
    font      = load_font(FONT_SIZE)
    font_info = load_font(FONT_SIZE_INFO)
    p    = shop["pos"]
    fix  = shop["fixed"]
    pc   = shop["product_codes"]

    transfer = int(data["transfer"])
    total    = transfer
    col_w = {
        "no":    p["row1_code"][0]  - p["row1_no"][0],
        "code":  p["row1_item"][0]  - p["row1_code"][0],
        "item":  p["row1_qty"][0]   - p["row1_item"][0],
        "qty":   p["row1_total"][0] - p["row1_qty"][0],
        "total": 260,
    }

    put(draw, data["name"],    p["name"],    font_info)
    put(draw, data["address"], p["address"], font_info)
    put(draw, data["phone"],   p["phone"],   font_info)
    put(draw, fix["track_no"], p["track_no"], font)
    put(draw, fix["order_no"], p["order_no"], font)
    put(draw, thai_date(),     p["date"],     font)

    row_keys = [
        ("row1_no","row1_code","row1_item","row1_qty","row1_total"),
        ("row2_no","row2_code","row2_item","row2_qty","row2_total"),
        ("row3_no","row3_code","row3_item","row3_qty","row3_total"),
        ("row4_no","row4_code","row4_item","row4_qty","row4_total"),
    ]
    products = data["products"] or [{"name":"แหวน","qty":"1","size":"","unit":""}]
    for i, prod in enumerate(products[:4]):
        rk = row_keys[i]
        code, full_name, unit = lookup_gold(prod["name"], pc)
        if prod.get("unit"): unit = prod["unit"]
        if prod.get("size"): full_name += f" (Size {prod['size']})"
        qty_val = prod.get("qty","1")
        put_center(draw, str(i+1),            p[rk[0]], font, col_w["no"])
        put_center(draw, code,                p[rk[1]], font, col_w["code"])
        put_center(draw, full_name,           p[rk[2]], font, col_w["item"])
        put_center(draw, f"{qty_val} {unit}", p[rk[3]], font, col_w["qty"])
        put_center(draw, fmt(total) if i==0 else "-", p[rk[4]], font, col_w["total"])

    put(draw, fmt(total),      p["grand_total"], font)
    put(draw, fix["discount"], p["discount"],    font)
    put(draw, fix["vat"],      p["vat"],         font)
    put(draw, fmt(total),      p["net_total"],   font)
    return img

# ============================================================
# 🤖 Handler
# ============================================================

def get_builder(shop_key):
    return make_gold if shop_key == "gold" else make_aircare

async def handle_message(update, context):
    text = update.message.text or ""
    shop_key = detect_shop(text)
    if not shop_key:
        return

    processing_msg = await update.message.reply_text("⏳ กำลังสร้างใบออเดอร์... รอสักครู่นะครับ")
    shop    = SHOPS[shop_key]
    builder = get_builder(shop_key)

    try:
        data = parse_order(text)
        img  = builder(data, shop)
    except FileNotFoundError as e:
        await processing_msg.delete()
        await update.message.reply_text(
            "❌ ไม่พบไฟล์ template หรือ font\n"
            f"รายละเอียด: {e}\n\n"
            "กรุณาวางไฟล์ต่อไปนี้ในโฟลเดอร์เดียวกับ bot.py\n"
            "• template_aircare.jpg\n• template_aircare_lab.jpg\n"
            "• template_levoit.jpg\n• template_gold.jpg\n• THSarabunNew.ttf"
        )
        return
    except Exception as e:
        await processing_msg.delete()
        await update.message.reply_text(
            f"⚠️ เกิดข้อผิดพลาด โปรดตรวจสอบข้อมูลของท่าน\nรายละเอียด: {e}"
        )
        return

    out = f"result_{shop_key}.jpg"
    img.save(out, quality=95)
    caption = (
        f"✅ {shop['display_name']}\n"
        f"👤 {data['name']}  📞 {data['phone']}\n"
        f"💰 โอน {fmt(data['transfer'])}  |  ปลายทาง {fmt(data['cod'])}\n\n"
        f"⚠️ โปรดตรวจสอบก่อนส่งให้ลูกค้า"
    )
    await processing_msg.delete()
    await update.message.reply_photo(
        photo=open(out,"rb"), caption=caption,
        reply_to_message_id=update.message.message_id
    )

# ============================================================
# 🚀 Main
# ============================================================

if __name__ == "__main__":
    print("✅ บอทเริ่มทำงานแล้ว...")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
