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
            print(f"⚠️ 打开失败，第{attempt + 1}次重试")
            time.sleep(2)

    return False


# ================== ⭐核心提取（完整版 - tr/td逻辑） ==================
def extract(page, item):
    try:
        # 遍历需要提取的属性
        for prop in ["发色", "瞳色", "萌点"]:

            # 使用 XPath 寻找包含该属性名的 tr 行（适配 td 或 th）
            xpath = f"//tr[td[normalize-space(text())='{prop}'] or th[normalize-space(text())='{prop}']]"
            row = page.locator(xpath).first

            if row.count() > 0:
                # 获取该行最后一个 td 单元格（存放具体数值的格子）
                value_cell = row.locator("td").last

                # 寻找格子内的 <a> 标签
                links = value_cell.locator("a")

                if links.count() > 0:
                    val_list = []
                    for j in range(links.count()):
                        val = clean_text(links.nth(j).inner_text())
                        # 去空 + 去重
                        if val and val != "未找到" and val not in val_list:
                            val_list.append(val)

                    if val_list:
                        item[prop] = "，".join(val_list)
                else:
                    # 如果没有 <a> 标签，直接抓取纯文本作为后备
                    val = clean_text(value_cell.inner_text())
                    if val and val != "未找到":
                        item[prop] = val

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