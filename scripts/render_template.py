#!/usr/bin/env python3
"""
Jinja2 模板渲染脚本
将 dashboard_data.json 的数据渲染到 HTML 模板中。

用法：
    python scripts/render_template.py --template template/dashboard.html.j2 --data data/dashboard_data.json --output dist/index.html
"""

import json
import argparse
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


def format_value(value, default="—"):
    """格式化数值，None 或空值显示默认占位符。"""
    if value is None or value == "":
        return default
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def none_to_dash(value):
    """Jinja2 filter: None 或空值转为 '—'。"""
    if value is None or value == "":
        return "—"
    return value


def format_datetime(iso_string):
    """将 ISO 日期字符串格式化为友好格式。"""
    if not iso_string:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return iso_string[:16] if len(iso_string) > 16 else iso_string


def format_date(iso_string):
    """将 ISO 日期字符串格式化为日期。"""
    if not iso_string:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return iso_string[:10] if len(iso_string) > 10 else iso_string


def main():
    parser = argparse.ArgumentParser(description="Render dashboard HTML template")
    parser.add_argument("--template", required=True, help="Jinja2 模板路径")
    parser.add_argument("--data", required=True, help="数据 JSON 路径")
    parser.add_argument("--output", required=True, help="输出 HTML 路径")
    args = parser.parse_args()

    # 读取数据
    with open(args.data, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 设置 Jinja2 环境
    template_dir = Path(args.template).parent
    template_name = Path(args.template).name
    env = Environment(loader=FileSystemLoader(template_dir))
    env.filters["format_value"] = format_value
    env.filters["format_datetime"] = format_datetime
    env.filters["format_date"] = format_date
    env.filters["none_to_dash"] = none_to_dash

    template = env.get_template(template_name)

    # 渲染
    html = template.render(
        data=data,
        generated_at=data.get("meta", {}).get("generated_at", datetime.now().isoformat()),
    )

    # 写入输出
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Rendered {args.template} -> {args.output}")


if __name__ == "__main__":
    main()
