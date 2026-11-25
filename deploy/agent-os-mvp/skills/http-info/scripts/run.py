from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from http.client import HTTPException
from unicodedata import category
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ENDPOINT = "https://earthquake.usgs.gov/fdsnws/event/1/query"
RADIUS_KM = 500
WINDOW_DAYS = 30  # The catalog's default time window.
TIMEOUT_SECONDS = 8
MAX_INPUT_BYTES = 4096
MAX_RESPONSE_BYTES = 32 * 1024


class QueryError(ValueError):
    pass


class RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_coordinates() -> tuple[float, float]:
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise QueryError("输入超过大小限制")
    try:
        data = json.loads(raw)
    except (ValueError, RecursionError):
        raise QueryError("请输入合法的 JSON 对象") from None
    if not isinstance(data, dict):
        raise QueryError("请输入 JSON 对象")
    if set(data) - {"latitude", "longitude"}:
        raise QueryError("只支持 latitude 和 longitude 两个参数")
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    if type(latitude) not in (int, float) or not -90 <= latitude <= 90:
        raise QueryError("latitude（纬度）必填，且必须是 -90 至 90 之间的数字")
    if type(longitude) not in (int, float) or not -180 <= longitude <= 180:
        raise QueryError("longitude（经度）必填，且必须是 -180 至 180 之间的数字")
    return latitude, longitude


def query_event(latitude: float, longitude: float) -> dict | None:
    query = urlencode(
        {
            "format": "geojson",
            "latitude": latitude,
            "longitude": longitude,
            "maxradiuskm": RADIUS_KM,
            "limit": 1,
            "orderby": "time",
            "eventtype": "earthquake",
            "nodata": 204,
        }
    )
    request = Request(f"{ENDPOINT}?{query}", headers={"Accept": "application/json"})
    opener = build_opener(ProxyHandler({}), RejectRedirects())
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            if response.status == 204:
                return None
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as error:
        error.close()
        raise QueryError(f"USGS 返回 HTTP {error.code}") from None
    except (URLError, OSError, HTTPException):
        raise QueryError("无法连接 USGS 或查询超时") from None
    if len(raw) > MAX_RESPONSE_BYTES:
        raise QueryError("USGS 响应超过大小限制")
    try:
        data = json.loads(raw)
        if data["type"] != "FeatureCollection":
            raise ValueError
        features = data["features"]
        if not isinstance(features, list) or len(features) > 1:
            raise ValueError
        if not features:
            return None
        properties = features[0]["properties"]
        place = properties["place"]
        magnitude = properties["mag"]
        timestamp = properties["time"]
        if place is not None and (not isinstance(place, str) or len(place) > 256):
            raise ValueError
        if place is not None:
            place = " ".join(place.split())
            place = "".join(char for char in place if not category(char).startswith("C")) or None
        if magnitude is not None and (type(magnitude) not in (int, float) or not math.isfinite(magnitude)):
            raise ValueError
        if type(timestamp) is not int:
            raise ValueError
        time_utc = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).isoformat(timespec="milliseconds")
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError, OSError):
        raise QueryError("USGS 返回的数据格式异常") from None
    return {"place": place, "magnitude": magnitude, "time_utc": time_utc}


def main() -> int:
    try:
        latitude, longitude = read_coordinates()
        event = query_event(latitude, longitude)
    except QueryError as error:
        print(error, file=sys.stderr)
        return 1
    area = f"纬度 {latitude}°、经度 {longitude}° 周边 {RADIUS_KM} 公里"
    if event is None:
        answer = f"{area}，USGS 地震目录最近 {WINDOW_DAYS} 天无匹配记录。"
    else:
        place = event["place"] or "地点未公布"
        magnitude = f"{event['magnitude']} 级" if event["magnitude"] is not None else "未公布"
        answer = (
            f"{area}，最近 {WINDOW_DAYS} 天内最新一条地震记录："
            f"{event['time_utc']}（UTC），{place}，震级 {magnitude}。数据来源：USGS 地震目录。"
        )
    print(
        json.dumps(
            {
                "source": "USGS 地震目录",
                "latitude": latitude,
                "longitude": longitude,
                "radius_km": RADIUS_KM,
                "window_days": WINDOW_DAYS,
                "event": event,
                "answer": answer,
            },
            ensure_ascii=False,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
