"""诊断 830-048 / Heyfield 系列名问题。在项目根目录运行: python tools/check_family.py"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

SKU = "830-048"


def ok(msg: str) -> None:
    print(f"  OK  {msg}")


def fail(msg: str) -> None:
    print(f"  !!  {msg}")


def main() -> int:
    print("=== 系列名诊断 (830-048 / Heyfield) ===\n")

    layout_py = os.path.join(ROOT, "layout.py")
    if os.path.isfile(layout_py):
        text = open(layout_py, encoding="utf-8").read()
        if "effective_family_from_display_item" in text:
            ok("layout.py 已是新版本（含系列名修复）")
        else:
            fail("layout.py 仍是旧版 — git 未更新成功，或 sparse-checkout 拦住了文件")
    else:
        fail("找不到 layout.py")

    tpl_path = os.path.join(ROOT, "furniture_templates.json")
    if os.path.isfile(tpl_path):
        data = json.load(open(tpl_path, encoding="utf-8"))
        entry = next((x for x in data if str(x.get("id", "")).strip() == SKU), None)
        if entry:
            fam = str(entry.get("product_family", "") or "").strip()
            if fam and fam != SKU and fam not in ("未分类", "nan"):
                ok(f"furniture_templates.json 中 {SKU} → product_family = {fam!r}")
            else:
                fail(
                    f"furniture_templates.json 中 {SKU} 的 product_family = {fam!r}（SKU 占位）"
                    " — 刷新布局后会自动修正；或手动改为 Heyfield"
                )
        else:
            fail(f"furniture_templates.json 里没有 {SKU}")
    else:
        fail("找不到 furniture_templates.json")

    display_xlsx = os.path.join(ROOT, "data", "display.xlsx")
    if os.path.isfile(display_xlsx):
        ok(f"存在 data/display.xlsx")
        try:
            from display_lookup import lookup_display_item, effective_family_from_display_item

            item = lookup_display_item(SKU)
            if item:
                fam = effective_family_from_display_item(item)
                ok(f"Display 大库: {item.product_name!r} → 系列 {fam!r}")
            else:
                fail(f"display.xlsx 里没有 {SKU} — 请运行 grab_display.bat 重新抓取")
        except Exception as exc:
            fail(f"读取 display.xlsx 失败: {exc}")
    else:
        fail("没有 data/display.xlsx — 请运行 grab_display.bat")

    try:
        from layout import effective_product_family

        resolved = effective_product_family(SKU, SKU)
        if resolved and resolved != SKU:
            ok(f"layout 解析结果: {SKU} → {resolved!r}")
        else:
            fail(f"layout 仍无法解析系列名（结果: {resolved!r}）→ 画布会显示「未分配」")
    except Exception as exc:
        fail(f"无法 import layout 测试: {exc}")

    westgate = os.path.join(ROOT, "data", "layouts", "westgate.json")
    if os.path.isfile(westgate):
        layout = json.load(open(westgate, encoding="utf-8"))
        placed = [f for f in layout.get("furnitures", []) if f.get("name") == SKU]
        if placed:
            fam = str(placed[0].get("product_family", "") or "").strip()
            if fam and fam not in (SKU, "nan", "未分类"):
                ok(f"westgate.json 已保存系列名: {fam!r}")
            else:
                fail(
                    f"westgate.json 里 {SKU} 的 product_family = {fam!r}"
                    " — 布局里点「刷新」后请「保存」"
                )
        else:
            print(f"  --  westgate.json 未摆放 {SKU}")

    print("\n=== 建议 ===")
    print("1. git reset --hard origin/master  （备份已在 backup_before_pull）")
    print("2. 不要恢复 backup 里的 furniture_templates.json / display.sql")
    print("3. 只恢复 data/layouts/*.json 门店布局")
    print("4. 运行 grab_display.bat")
    print("5. 重开 Layout → 刷新 → 保存")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
