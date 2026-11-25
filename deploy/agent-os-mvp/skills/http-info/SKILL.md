---
name: http-info
description: 按指定经纬度查询美国地质调查局公开地震目录，用于验证云端 HTTP 查询和结构化参数调用。
---

# HTTP 查询（地震目录）

执行 `scripts/run.py`。通过标准输入提供一个 JSON 对象，两个字段都必填，值必须是 JSON 数字。

| 字段 | 含义 | 范围 |
| --- | --- | --- |
| `latitude` | 纬度（度） | -90 至 90 |
| `longitude` | 经度（度） | -180 至 180 |

```sh
printf '%s\n' '{"latitude":35.68,"longitude":139.69}' | python3 scripts/run.py
```

脚本以固定 HTTPS GET 查询坐标 500 公里内最近 30 天目录中时间最新的一条地震。成功时标准输出为单个 JSON 对象，`event` 保存事件时间（UTC）、地点和震级，无匹配时为 `null`。直接使用 `answer` 展示中文结果。失败时退出码非零，标准错误说明原因。结果用于轻量联调，来源为 [USGS 地震目录](https://earthquake.usgs.gov/fdsnws/event/1/)。
