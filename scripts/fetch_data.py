#!/usr/bin/env python3
"""
飞书 Base 数据拉取脚本
从飞书 Base 读取数据，处理后输出为 JSON 供模板渲染使用。

环境变量：
    LARK_APP_ID      - 飞书开放平台 App ID
    LARK_APP_SECRET  - 飞书开放平台 App Secret
    LARK_BASE_TOKEN  - 飞书 Base Token（可选，默认使用 config/base_mapping.json 中的值）

用法：
    python scripts/fetch_data.py --output data/dashboard_data.json
"""

import os
import sys
import json
import time
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

LARK_API_BASE = "https://open.feishu.cn/open-apis"
MAX_RETRIES = 3
RETRY_DELAY = 2
RATE_LIMIT_DELAY = 0.5  # 表间拉取间隔，避免触发速率限制


def parse_date_safe(date_str):
    """安全解析日期字符串或时间戳，支持多种常见格式。"""
    if not date_str:
        return None
    # 处理整数/浮点数时间戳（毫秒或秒）
    if isinstance(date_str, (int, float)):
        ts = date_str
        # 毫秒时间戳（13位）
        if ts > 1e10:
            ts = ts / 1000.0
        return datetime.fromtimestamp(ts)
    # 确保是字符串
    date_str = str(date_str).strip()
    formats = (
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d",
    )
    for fmt in formats:
        try:
            return datetime.strptime(date_str[: len(fmt)], fmt)
        except ValueError:
            continue
    # 尝试截断时区偏移后解析
    if "T" in date_str:
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            pass
    return None


def get_tenant_access_token(app_id: str, app_secret: str) -> str:
    """获取 tenant_access_token（应用级凭证）。"""
    url = f"{LARK_API_BASE}/auth/v3/tenant_access_token/internal"
    payload = {"app_id": app_id, "app_secret": app_secret}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(url, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") == 0:
                token = data["tenant_access_token"]
                logger.info("Tenant access token acquired")
                return token
            logger.warning(f"Token request failed: {data.get('msg')} (attempt {attempt})")
        except requests.RequestException as e:
            logger.warning(f"Token request error: {e} (attempt {attempt})")

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY * attempt)

    raise RuntimeError("Failed to obtain tenant access token after retries")


def fetch_records(token: str, base_token: str, table_id: str, fields: list) -> list:
    """分页拉取 Base 表中的记录。"""
    headers = {"Authorization": f"Bearer {token}"}
    records = []
    has_more = True
    page_token = None

    # 飞书分页 limit 上限为 500
    limit = 500

    while has_more:
        params = {
            "page_size": limit,
        }
        if page_token:
            params["page_token"] = page_token

        url = f"{LARK_API_BASE}/bitable/v1/apps/{base_token}/tables/{table_id}/records"

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=30)

                # 处理 HTTP 429 速率限制
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    wait = int(retry_after) if retry_after and retry_after.isdigit() else RETRY_DELAY * attempt
                    logger.warning(f"Rate limited (429), waiting {wait}s before retry {attempt}")
                    time.sleep(wait)
                    continue

                resp.raise_for_status()
                data = resp.json()

                if data.get("code") != 0:
                    logger.warning(
                        f"Fetch records error: {data.get('msg')} (attempt {attempt})"
                    )
                    if attempt < MAX_RETRIES:
                        time.sleep(RETRY_DELAY * attempt)
                        continue
                    raise RuntimeError(f"API error: {data.get('msg')}")

                items = data["data"].get("items", [])
                for item in items:
                    record_fields = item.get("fields", {})
                    # 只保留用户配置的 fields，不暴露内部 record_id
                    record = {f: record_fields.get(f) for f in fields}
                    records.append(record)

                has_more = data["data"].get("has_more", False)
                page_token = data["data"].get("page_token")
                logger.info(
                    f"Fetched {len(items)} records from {table_id}, total={len(records)}, has_more={has_more}"
                )
                break

            except requests.RequestException as e:
                logger.warning(f"Request error: {e} (attempt {attempt})")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)
                else:
                    raise

    return records


def process_environment(env_records: list) -> dict:
    """处理环境参数数据：计算每日均值、最新值。"""
    if not env_records:
        return {"trend": [], "latest": {}}

    # 按日期聚合
    daily = {}
    for r in env_records:
        t = r.get("record_time", "")
        if not t:
            continue
        # 安全解析日期
        dt = parse_date_safe(t)
        if dt:
            date = dt.strftime("%Y-%m-%d")
        elif isinstance(t, str) and len(t) >= 10:
            date = t[:10]
        else:
            date = str(t)[:10] if t else ""
        if date not in daily:
            daily[date] = {"temps": [], "humidities": [], "ammonias": []}
        if r.get("temperature") is not None:
            try:
                daily[date]["temps"].append(float(r["temperature"]))
            except (ValueError, TypeError):
                pass
        if r.get("humidity") is not None:
            try:
                daily[date]["humidities"].append(float(r["humidity"]))
            except (ValueError, TypeError):
                pass
        if r.get("ammonia") is not None:
            try:
                daily[date]["ammonias"].append(float(r["ammonia"]))
            except (ValueError, TypeError):
                pass

    trend = []
    for date in sorted(daily.keys()):
        d = daily[date]
        trend.append({
            "date": date,
            "temperature_avg": round(sum(d["temps"]) / len(d["temps"]), 2) if d["temps"] else None,
            "humidity_avg": round(sum(d["humidities"]) / len(d["humidities"]), 2) if d["humidities"] else None,
            "ammonia_avg": round(sum(d["ammonias"]) / len(d["ammonias"]), 2) if d["ammonias"] else None,
        })

    # 最新值
    sorted_records = sorted(
        [r for r in env_records if r.get("record_time")],
        key=lambda x: x["record_time"],
        reverse=True,
    )
    latest = sorted_records[0] if sorted_records else {}

    return {"trend": trend, "latest": latest}


def process_farming(events: list) -> dict:
    """处理养殖事件：统计各类事件数量。"""
    if not events:
        return {"total": 0, "by_type": [], "recent": []}

    # 按类型统计
    type_counts = {}
    for r in events:
        et = r.get("event_type")
        if isinstance(et, list):
            for t in et:
                type_counts[t] = type_counts.get(t, 0) + 1
        elif et:
            type_counts[et] = type_counts.get(et, 0) + 1

    by_type = [{"type": k, "count": v} for k, v in type_counts.items()]
    by_type.sort(key=lambda x: x["count"], reverse=True)

    # 最近事件
    recent = sorted(
        [r for r in events if r.get("event_date")],
        key=lambda x: x["event_date"],
        reverse=True,
    )[:10]

    return {"total": len(events), "by_type": by_type, "recent": recent}


def process_health(health_records: list) -> dict:
    """处理健康记录：统计健康状态分布。"""
    if not health_records:
        return {"total": 0, "status_distribution": [], "latest": []}

    status_counts = {}
    for r in health_records:
        st = r.get("health_status")
        if isinstance(st, list):
            for s in st:
                status_counts[s] = status_counts.get(s, 0) + 1
        elif st:
            status_counts[st] = status_counts.get(st, 0) + 1

    status_distribution = [{"status": k, "count": v} for k, v in status_counts.items()]

    latest = sorted(
        [r for r in health_records if r.get("record_date")],
        key=lambda x: x["record_date"],
        reverse=True,
    )[:10]

    return {
        "total": len(health_records),
        "status_distribution": status_distribution,
        "latest": latest,
    }


def process_feed(feed_records: list) -> dict:
    """处理饲料消耗：聚合历史数据 + 简单线性预测未来7天。"""
    if not feed_records:
        return {"history": [], "predicted": []}

    sorted_records = sorted(
        [r for r in feed_records if r.get("record_date")],
        key=lambda x: parse_date_safe(x.get("record_date")) or "",
    )

    history = []
    for r in sorted_records:
        def to_float(v):
            if v is None:
                return None
            try:
                return float(v)
            except (ValueError, TypeError):
                return None
        dt = parse_date_safe(r.get("record_date"))
        date_str = dt.strftime("%Y-%m-%d") if dt else ""
        history.append({
            "date": date_str,
            "feed_quantity_kg": to_float(r.get("feed_quantity_kg")),
            "avg_intake_kg": to_float(r.get("avg_intake_kg")),
            "animal_count": to_float(r.get("animal_count")),
            "feed_cost": to_float(r.get("feed_cost")),
            "predicted": False,
        })

    # 简单线性预测未来7天（基于最近30天数据，最少2天）
    predicted = []
    valid_history = [h for h in history if h["feed_quantity_kg"] is not None]
    if len(valid_history) >= 2:
        try:
            import numpy as np
            y = np.array([h["feed_quantity_kg"] for h in valid_history])
            x = np.arange(len(y))
            window = min(30, len(y))
            coeffs = np.polyfit(x[-window:], y[-window:], 1)
            last_date = datetime.strptime(valid_history[-1]["date"], "%Y-%m-%d")
            for i in range(1, 8):
                pred_date = (last_date + timedelta(days=i)).strftime("%Y-%m-%d")
                pred_val = float(np.polyval(coeffs, len(y) - 1 + i))
                predicted.append({
                    "date": pred_date,
                    "feed_quantity_kg": round(max(pred_val, 0), 2),
                    "predicted": True,
                })
        except ImportError:
            logger.warning("numpy not available, skipping prediction")
        except Exception as e:
            logger.warning(f"Prediction failed: {e}")

    return {"history": history, "predicted": predicted}


def process_market(market_records: list) -> dict:
    """处理行情数据：按指标计算均值，取前6项。"""
    if not market_records:
        return {"radar": [], "latest_date": ""}

    indicators = {}
    for r in market_records:
        ind = r.get("indicator")
        if not ind:
            continue
        if ind not in indicators:
            indicators[ind] = {"values": [], "unit": r.get("unit", ""), "category": r.get("category", "")}
        if r.get("value") is not None:
            try:
                indicators[ind]["values"].append(float(r["value"]))
            except (ValueError, TypeError):
                pass

    radar = []
    for ind, data in indicators.items():
        if data["values"]:
            radar.append({
                "indicator": ind,
                "avg": round(sum(data["values"]) / len(data["values"]), 2),
                "latest": data["values"][-1],
                "unit": data["unit"],
                "category": data["category"],
            })

    radar.sort(key=lambda x: x["avg"], reverse=True)
    radar = radar[:6]

    # 最新数据日期
    dates = [r.get("data_date", "") for r in market_records if r.get("data_date")]
    latest_date = max(dates) if dates else ""

    return {"radar": radar, "latest_date": latest_date}


def process_alerts(alerts: list) -> dict:
    """处理告警记录：统计级别分布和最新告警。"""
    if not alerts:
        return {"total": 0, "by_level": [], "by_type": [], "latest": [], "unhandled": 0}

    level_counts = {}
    type_counts = {}
    unhandled = 0
    for r in alerts:
        lv = r.get("alert_level")
        if isinstance(lv, list):
            for l in lv:
                level_counts[l] = level_counts.get(l, 0) + 1
        elif lv:
            level_counts[lv] = level_counts.get(lv, 0) + 1

        at = r.get("alert_type")
        if isinstance(at, list):
            for t in at:
                type_counts[t] = type_counts.get(t, 0) + 1
        elif at:
            type_counts[at] = type_counts.get(at, 0) + 1

        status = r.get("status")
        if isinstance(status, list):
            if not status or "未处理" in status:
                unhandled += 1
        elif not status or status == "未处理":
            unhandled += 1

    by_level = [{"level": k, "count": v} for k, v in level_counts.items()]
    by_type = [{"type": k, "count": v} for k, v in type_counts.items()]

    latest = sorted(
        [r for r in alerts if r.get("alert_time")],
        key=lambda x: x["alert_time"],
        reverse=True,
    )[:10]

    return {
        "total": len(alerts),
        "by_level": by_level,
        "by_type": by_type,
        "latest": latest,
        "unhandled": unhandled,
    }


def compute_kpi(env: dict, farming: dict, alerts: dict, feed: dict) -> dict:
    """计算 KPI 指标。"""
    latest = env.get("latest", {})
    total_animals = None
    if feed.get("history"):
        total_animals = feed["history"][-1].get("animal_count")

    # 死淘率 = (死亡数 + 淘汰数) / 存栏总数
    death_rate = None
    if total_animals and total_animals > 0:
        death_count = sum(t["count"] for t in farming.get("by_type", []) if t["type"] in ("死亡", "淘汰"))
        death_rate = round(death_count / total_animals * 100, 2)

    return {
        "total_animals": total_animals,
        "death_rate": death_rate,
        "alert_count": alerts.get("total", 0),
        "unhandled_alerts": alerts.get("unhandled", 0),
        "latest_temperature": latest.get("temperature"),
        "latest_humidity": latest.get("humidity"),
        "latest_ammonia": latest.get("ammonia"),
        "latest_env_time": latest.get("record_time"),
    }


def main():
    parser = argparse.ArgumentParser(description="Fetch Feishu Base data for dashboard")
    parser.add_argument("--config", default="config/base_mapping.json", help="配置文件路径")
    parser.add_argument("--output", default="data/dashboard_data.json", help="输出JSON路径")
    parser.add_argument("--app-id", default=os.environ.get("LARK_APP_ID"), help="飞书 App ID")
    parser.add_argument("--app-secret", default=os.environ.get("LARK_APP_SECRET"), help="飞书 App Secret")
    parser.add_argument("--base-token", default=os.environ.get("LARK_BASE_TOKEN"), help="Base Token")
    args = parser.parse_args()

    # 读取配置
    config_path = Path(args.config)
    if not config_path.exists():
        logger.error(f"Config file not found: {config_path}")
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)

    # 凭证优先级：命令行 > 环境变量 > 配置文件
    app_id = args.app_id or os.environ.get("LARK_APP_ID")
    app_secret = args.app_secret or os.environ.get("LARK_APP_SECRET")
    base_token = args.base_token or os.environ.get("LARK_BASE_TOKEN") or config.get("base_token")

    if not app_id or not app_secret:
        logger.error("Missing LARK_APP_ID or LARK_APP_SECRET. Please set them as environment variables or pass via --app-id / --app-secret")
        sys.exit(1)

    if not base_token:
        logger.error("Missing Base token. Please set LARK_BASE_TOKEN or configure in base_mapping.json")
        sys.exit(1)

    # 获取 token
    token = get_tenant_access_token(app_id, app_secret)

    # 拉取所有表数据
    raw_data = {}
    for idx, table_config in enumerate(config.get("tables", [])):
        name = table_config["name"]
        table_id = table_config["table_id"]
        fields = table_config.get("fields", [])
        logger.info(f"Fetching table: {name} ({table_id})")
        records = fetch_records(token, base_token, table_id, fields)
        raw_data[name] = records
        # 表间添加延迟，避免触发飞书 API 速率限制
        if idx < len(config.get("tables", [])) - 1:
            time.sleep(RATE_LIMIT_DELAY)

    # 处理数据
    env_data = process_environment(raw_data.get("environment_params", []))
    farming_data = process_farming(raw_data.get("farming_events", []))
    health_data = process_health(raw_data.get("animal_health", []))
    feed_data = process_feed(raw_data.get("feed_consumption", []))
    market_data = process_market(raw_data.get("market_data", []))
    alert_data = process_alerts(raw_data.get("alert_record", []))
    kpi = compute_kpi(env_data, farming_data, alert_data, feed_data)

    # 构建输出 — 注意：不在任何输出中包含 base_token
    dashboard_data = {
        "kpi": kpi,
        "environment": env_data,
        "farming": farming_data,
        "health": health_data,
        "feed": feed_data,
        "market": market_data,
        "alerts": alert_data,
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "data_source": "Feishu Base",
        },
    }

    # 确保输出目录存在
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(dashboard_data, f, ensure_ascii=False, indent=2)

    logger.info(f"Dashboard data written to {output_path}")
    logger.info(f"Records summary: env={len(raw_data.get('environment_params', []))}, "
                f"farming={len(raw_data.get('farming_events', []))}, "
                f"health={len(raw_data.get('animal_health', []))}, "
                f"feed={len(raw_data.get('feed_consumption', []))}, "
                f"market={len(raw_data.get('market_data', []))}, "
                f"alerts={len(raw_data.get('alert_record', []))}")


if __name__ == "__main__":
    main()
