import pandas as pd
import time
import re
import random
from playwright.sync_api import sync_playwright


# ================== 清洗 ==================
def clean_text(t):
    if not t:
        return "未找到"
    t = re.sub(r'\[\d+\]', '', t)
    return t.strip()


# ================== 打开页面 ==================
def open_page(page, name):
    url = f"https://zh.moegirl.org.cn/{name}"

    for attempt in range(2):
        try:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)

            html = page.content()

            # Cloudflare 检测
            if "Just a moment" in html or "cf-" in html:
                print("🚫 被拦截")
                return False

            # 页面不存在
            if "不存在" in page.title():
                return False

            return True

        except:
            print(f"⚠️ 打开失败，第{attempt+1}次重试")
            time.sleep(2)

    return False


# ================== ⭐核心提取（完整版） ==================
def extract(page, item):
    try:
        labels = page.locator("span")

        for i in range(labels.count()):
            text = labels.nth(i).inner_text().strip()

            # 找到对应模块（向上两层）
            parent = labels.nth(i).locator("xpath=../..")

            # ===== 发色 =====
            if text == "发色":
                links = parent.locator("a")
                if links.count() > 0:
                    item["发色"] = clean_text(links.first.inner_text())

            # ===== 瞳色 =====
            elif text == "瞳色":
                links = parent.locator("a")
                if links.count() > 0:
                    item["瞳色"] = clean_text(links.first.inner_text())

            # ===== ⭐萌点（完整抓取）=====
            elif text == "萌点":
                links = parent.locator("a")

                moe_list = []

                for j in range(links.count()):  # ✅ 不限制数量
                    val = clean_text(links.nth(j).inner_text())

                    # 去空 + 去重
                    if val and val not in moe_list:
                        moe_list.append(val)

                item["萌点"] = "，".join(moe_list)

        return True

    except Exception as e:
        print("❌ 提取异常:", e)
        return False


# ================== 主程序 ==================
def scrape():
    input_file = "names.xlsx"
    output_file = "results.xlsx"

    try:
        df = pd.read_excel(input_file)
        names = df["姓名"].dropna().tolist()
    except Exception as e:
        print("❌ Excel读取失败:", e)
        return

    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # 👉 显示浏览器
        context = browser.new_context()
        page = context.new_page()

        print(f"🚀 开始抓取 {len(names)} 条")

        for name in names:
            name = str(name).strip()

            item = {
                "姓名": name,
                "发色": "未找到",
                "瞳色": "未找到",
                "萌点": "未找到"
            }

            print(f"\n📡 查询: {name}")

            success = open_page(page, name)

            if not success:
                print("❌ 页面失败或不存在")
                results.append(item)
                continue

            ok = extract(page, item)

            print(f"🎯 结果: 发色={item['发色']} 瞳色={item['瞳色']} 萌点={item['萌点']}")

            results.append(item)

            time.sleep(2 + random.uniform(1, 2))

        browser.close()

    pd.DataFrame(results).to_excel(output_file, index=False)
    print(f"\n🎉 完成，已保存到 {output_file}")


# ================== 测试 ==================
def test():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        page.goto("https://zh.moegirl.org.cn/初音未来", timeout=60000)

        print("标题:", page.title())

        input("回车关闭...")
        browser.close()


# ================== 入口 ==================
if __name__ == "__main__":
    #test()      # 👉 先测试浏览器
    scrape()  # 👉 测试OK后再运行