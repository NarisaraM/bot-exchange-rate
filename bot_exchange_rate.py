"""
Fetch Bank of Thailand daily exchange rates and append them to a text file.

Data source: the JSON endpoint that
https://www.bot.or.th/th/statistics/exchange-rate.html itself calls.
It returns the most recently published day's rates (commercial-bank average,
Bangkok) for ~50 currencies, plus the weighted-average interbank USD/THB rate
(the "อัตราแลกเปลี่ยนถัวเฉลี่ยถ่วงน้ำหนักระหว่างธนาคาร" figure shown at the top
of the page), which is carried inside the JSON's "description" HTML.

No third-party packages required (uses only the standard library).

Output columns (tab-separated):
    date  currency  buying_sight  buying_transfer  selling  weighted_avg_interbank  fetched_at_utc

`weighted_avg_interbank` is a USD/THB-only figure, so it is filled in on the USD
row and left as "-" for every other currency.

Usage:
    python bot_exchange_rate.py                 # append USD row (incl. weighted avg)
    python bot_exchange_rate.py USD EUR JPY     # append several currencies
    python bot_exchange_rate.py --all           # append every currency
    python bot_exchange_rate.py --file rates.txt USD
"""

# ---------------------------------------------------------------------------
# STEP 1: import ไลบรารีมาตรฐานที่ต้องใช้ (ไม่มีตัวไหนต้อง pip install)
# ---------------------------------------------------------------------------
import argparse          # อ่าน argument ที่ผู้ใช้พิมพ์ต่อท้ายคำสั่ง
import json              # แปลงข้อความ JSON <-> โครงสร้างข้อมูล Python (dict/list)
import os                # ตรวจว่าไฟล์มีอยู่ไหม / หา path เต็มของไฟล์
import re                # regular expression ใช้ตัด HTML tag ออกจากข้อความ
import sys               # เข้าถึง stdout/stderr และกำหนด exit code ของโปรเซส
import urllib.request    # ยิง HTTP request ไปดึงข้อมูล (ไม่ต้องพึ่ง requests)
from datetime import datetime, timezone   # เอาเวลาปัจจุบันแบบ UTC มาบันทึก

# ---------------------------------------------------------------------------
# STEP 2: บังคับให้หน้าจอ (console) แสดงผลเป็น UTF-8
# Windows terminal มักตั้งค่า code page เป็นแบบเก่า พอ print ภาษาไทยจะเพี้ยน
# จึงสั่ง reconfigure ทั้ง stdout และ stderr; ถ้า Python เก่าทำไม่ได้ก็ปล่อยผ่าน
# ---------------------------------------------------------------------------
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

# ---------------------------------------------------------------------------
# STEP 3: ค่าคงที่ของโปรแกรม
# ---------------------------------------------------------------------------
# URL ของไฟล์ JSON ที่ ธปท. ใช้ป้อนข้อมูลให้หน้าเว็บอัตราแลกเปลี่ยน
URL = (
    "https://www.bot.or.th/content/bot/th/statistics/exchange-rate/"
    "jcr:content/root/container/statisticstable2.results.level3cache.json"
)

DEFAULT_OUTFILE = "thb_exchange_rate.txt"   # ชื่อไฟล์ผลลัพธ์เริ่มต้น
DEFAULT_CURRENCIES = ["USD"]                # ถ้าไม่ระบุสกุลเงิน จะบันทึกแค่ USD

# บรรทัดหัวตารางของไฟล์ผลลัพธ์ แต่ละคอลัมน์คั่นด้วย tab (\t)
HEADER = ("# date\tcurrency\tbuying_sight\tbuying_transfer\tselling"
          "\tweighted_avg_interbank\tfetched_at_utc\n")


# ===========================================================================
# STEP 4: ฟังก์ชันดึงข้อมูลดิบจาก ธปท.
# ===========================================================================
def fetch_payload():
    """ยิง HTTP GET ไปที่ URL แล้วคืนค่า JSON ที่แปลงเป็น dict ของ Python ทั้งก้อน"""
    # 4.1 สร้าง request พร้อมแนบ header (บาง server บล็อกถ้าไม่มี User-Agent)
    req = urllib.request.Request(
        URL,
        headers={
            "User-Agent": "Mozilla/5.0 (exchange-rate-logger)",
            "Accept": "application/json",
        },
    )
    # 4.2 เปิดการเชื่อมต่อ ถ้าเกิน 30 วินาทีให้โยน error ออกมา
    with urllib.request.urlopen(req, timeout=30) as resp:
        # 4.3 อ่าน response ทั้งหมดแล้ว parse JSON -> คืนออกไป
        return json.load(resp)


# ===========================================================================
# STEP 5: ฟังก์ชันแกะค่า "อัตราถัวเฉลี่ยถ่วงน้ำหนักระหว่างธนาคาร" ออกจาก HTML
# ธปท. ส่งค่านี้มาปนอยู่ในฟิลด์ description เช่น:
#   <p>อัตราแลกเปลี่ยนถัวเฉลี่ยถ่วงน้ำหนักระหว่างธนาคาร&nbsp;
#   <span ...>32.932</span>&nbsp;บาท ต่อ 1 ดอลลาร์ สรอ.</p>
# ===========================================================================
def parse_weighted_avg(description):
    # 5.1 ถ้าไม่มีข้อความมาเลย คืน "-" (ไม่มีข้อมูล)
    if not description:
        return "-"
    # 5.2 ลบทุกอย่างที่อยู่ในเครื่องหมาย <...> ทิ้ง (คือ HTML tag)
    text = re.sub(r"<[^>]+>", " ", description)
    # 5.3 แทน &nbsp; (ช่องว่างแบบ HTML) ด้วยช่องว่างปกติ
    text = text.replace("&nbsp;", " ")
    # 5.4 หาเลขทศนิยมตัวแรกในข้อความ เช่น 32.932
    match = re.search(r"\d+\.\d+", text)
    # 5.5 เจอ -> คืนตัวเลขนั้น, ไม่เจอ -> คืน "-"
    return match.group(0) if match else "-"


# ===========================================================================
# STEP 6: ฟังก์ชันอ่านไฟล์เดิม เพื่อจำว่ามี "วันที่+สกุลเงิน" ไหนบันทึกไปแล้ว
# ใช้กันการเขียนข้อมูลซ้ำเวลารันหลายรอบในวันเดียวกัน
# ===========================================================================
def load_existing_keys(path):
    keys = set()
    # 6.1 ถ้าไฟล์ยังไม่เคยมี -> ไม่มีอะไรซ้ำ คืน set ว่าง
    if not os.path.exists(path):
        return keys
    # 6.2 เปิดไฟล์อ่านทีละบรรทัด
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            # 6.3 ข้ามบรรทัดว่าง และบรรทัด header ที่ขึ้นต้นด้วย #
            if not line or line.startswith("#"):
                continue
            # 6.4 แยกคอลัมน์ด้วย tab แล้วเก็บ key รูปแบบ "วันที่|สกุลเงิน"
            parts = line.split("\t")
            if len(parts) >= 2:
                keys.add(f"{parts[0]}|{parts[1]}")
    # 6.5 คืน set ของ key ที่มีอยู่แล้วทั้งหมด
    return keys


# ===========================================================================
# STEP 7: ฟังก์ชันหลัก - ควบคุมลำดับการทำงานทั้งหมด
# ===========================================================================
def main():
    # -- STEP 7.1: ตั้งค่าตัวอ่าน argument จาก command line -------------------
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("currencies", nargs="*", default=None,
                        help="Currency codes to record (default: USD)")   # สกุลเงิน 0 ตัวขึ้นไป
    parser.add_argument("--all", action="store_true",
                        help="Record every currency returned by BOT")     # เอาทุกสกุล
    parser.add_argument("--file", default=DEFAULT_OUTFILE,
                        help=f"Output text file (default: {DEFAULT_OUTFILE})")  # เปลี่ยนไฟล์ปลายทาง
    args = parser.parse_args()   # อ่านค่าที่ผู้ใช้พิมพ์จริง

    # -- STEP 7.2: ตัดสินใจว่าจะบันทึกสกุลเงินไหนบ้าง -----------------------
    # ใส่ --all  -> wanted = None (แปลว่า "เอาทุกสกุล")
    # ไม่ใส่     -> wanted = เซ็ตของสกุลที่ขอ (แปลงเป็นตัวพิมพ์ใหญ่) หรือ USD ถ้าไม่ระบุ
    wanted = None
    if not args.all:
        wanted = {c.upper() for c in (args.currencies or DEFAULT_CURRENCIES)}

    # -- STEP 7.3: ดึงข้อมูลจาก ธปท. (ถ้าล้มเหลวให้จบโปรแกรมด้วย exit code 1) --
    try:
        payload = fetch_payload()
    except Exception as exc:  # noqa: BLE001 - report any network/parse failure plainly
        print(f"ERROR: could not fetch rates: {exc}", file=sys.stderr)
        return 1

    # -- STEP 7.4: หยิบ 3 ส่วนที่ต้องใช้ออกจาก payload --------------------
    records = payload.get("responseContent", [])          # list ของเรตทุกสกุลเงิน
    last_updated = payload.get("lastUpdated", "")          # วันที่ ธปท. อัปเดต (ข้อความไทย)
    weighted_avg = parse_weighted_avg(payload.get("description", ""))  # ค่าถัวเฉลี่ยถ่วงน้ำหนัก

    # -- STEP 7.5: ถ้าไม่มีข้อมูลเรตเลย ให้จบด้วย error -------------------
    if not records:
        print("ERROR: endpoint returned no rate data", file=sys.stderr)
        return 1

    # -- STEP 7.6: เตรียมข้อมูลก่อนเขียนไฟล์ -----------------------------
    existing = load_existing_keys(args.file)              # key ที่บันทึกไว้แล้ว (กันซ้ำ)
    new_header = not os.path.exists(args.file)            # ไฟล์ยังไม่มี -> ต้องเขียน header
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")  # เวลาตอนดึงข้อมูล

    # วันที่ของงวดข้อมูลนี้ (รูปแบบ ISO เช่น 2026-09-04) หยิบจาก record ตัวแรก
    pub_date = records[0].get("period", "")

    # -- STEP 7.7: วนสร้างแถวข้อมูลใหม่ทีละสกุลเงิน --------------------
    rows = []
    usd_emitted = False   # ธงบอกว่าได้สร้างแถว USD แล้วหรือยัง
    for rec in records:
        code = rec.get("currency_id", "").upper()   # รหัสสกุลเงิน เช่น USD

        # 7.7a ถ้ากำหนดสกุลไว้ และตัวนี้ไม่อยู่ในลิสต์ที่ขอ -> ข้าม
        if wanted is not None and code not in wanted:
            continue

        date = rec.get("period", "")   # วันที่ของเรตแถวนี้ (ISO)
        key = f"{date}|{code}"

        # 7.7b ถ้า "วันที่+สกุลเงิน" นี้เคยบันทึกแล้ว -> ข้าม (กันซ้ำ)
        if key in existing:
            continue

        # 7.7c ต่อสตริง 7 คอลัมน์ด้วย tab แล้วเก็บเข้า rows
        #      คอลัมน์ weighted_avg ใส่ค่าจริงเฉพาะแถว USD นอกนั้นเป็น "-"
        rows.append("\t".join([
            date,
            code,
            rec.get("buying_sight", "-"),
            rec.get("buying_transfer", "-"),
            rec.get("selling", "-"),
            weighted_avg if code == "USD" else "-",
            fetched_at,
        ]))
        existing.add(key)              # จำ key นี้ไว้ กันซ้ำในรอบเดียวกัน
        if code == "USD":
            usd_emitted = True

    # -- STEP 7.8: ถ้าไม่ได้ขอ USD ก็ยังบันทึกค่าถัวเฉลี่ยถ่วงน้ำหนักไว้ --
    #    โดยเพิ่มแถว USD พิเศษที่มีแต่ค่านี้ (เรตอื่นเป็น "-") เพื่อไม่ให้ค่าหาย
    if not usd_emitted and weighted_avg != "-" and f"{pub_date}|USD" not in existing:
        rows.append("\t".join([
            pub_date, "USD", "-", "-", "-", weighted_avg, fetched_at,
        ]))
        existing.add(f"{pub_date}|USD")

    # -- STEP 7.9: ถ้าไม่มีแถวใหม่เลย -> แจ้งแล้วจบแบบสำเร็จ (exit code 0) --
    if not rows:
        print(f"Nothing new to add (BOT last updated: {last_updated}).")
        return 0

    # -- STEP 7.10: เขียนต่อท้ายไฟล์ (โหมด "a" = append) ----------------
    with open(args.file, "a", encoding="utf-8") as fh:
        if new_header:                 # ถ้าเป็นไฟล์ใหม่ ใส่บรรทัดหัวตารางก่อน
            fh.write(HEADER)
        for row in rows:              # เขียนทีละแถว แถวละบรรทัด
            fh.write(row + "\n")

    # -- STEP 7.11: พิมพ์สรุปผลลงหน้าจอ -------------------------------
    print(f"BOT last updated: {last_updated}")
    print(f"Weighted-average interbank USD/THB: {weighted_avg}")
    print(f"Appended {len(rows)} row(s) to {os.path.abspath(args.file)}:")
    for row in rows:
        print("  " + row.replace("\t", "  "))   # แปลง tab เป็นเว้นวรรคให้อ่านง่าย
    return 0   # จบแบบสำเร็จ


# ===========================================================================
# STEP 8: จุดเริ่มโปรแกรม - รันเฉพาะตอนสั่งไฟล์นี้ตรง ๆ (ไม่ใช่ตอนถูก import)
# เอาค่าที่ main() คืน (0 หรือ 1) ไปเป็น exit code ของโปรเซส
# ===========================================================================
if __name__ == "__main__":
    raise SystemExit(main())
