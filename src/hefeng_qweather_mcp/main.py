"""
Author: yeisme
Version: 0.3.3
License: MIT
"""

import httpx
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv
import logging
import os
import time
from datetime import datetime, timedelta, timezone
import jwt
from typing import Optional, Dict, Any
import typer

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("hefeng_qweather_mcp")

# 加载环境变量
# 尝试从多个位置加载 .env 文件以提高鲁棒性
load_dotenv()  # 默认：当前工作目录
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))  # 项目根目录

# 初始化MCP服务
mcp = FastMCP("hefeng_qweather_mcp")
app = typer.Typer()


# API配置常量
DEFAULT_FORECAST_DAYS = 3  # 默认天气预报天数
DEFAULT_SOLAR_HOURS = 24  # 默认太阳辐射预报小时数

# POI类型常量 - 基于和风天气官方API文档
POI_TYPES = {
    "scenic": "景点",
    "TSTA": "潮汐站点"
}

# 从环境变量获取API配置
api_host = os.environ.get("HEFENG_API_HOST")
api_key = os.environ.get("HEFENG_API_KEY")
project_id = os.environ.get("HEFENG_PROJECT_ID")
key_id = os.environ.get("HEFENG_KEY_ID")
private_key_path = os.environ.get("HEFENG_PRIVATE_KEY_PATH")
private_key_str = os.environ.get("HEFENG_PRIVATE_KEY")

# 验证必需的环境变量
if not api_host:
    raise ValueError("HEFENG_API_HOST 环境变量未设置")

# 优先使用API KEY认证，如果不可用则使用JWT认证
if api_key:
    # 使用API KEY认证（推荐）
    auth_header = {"X-QW-Api-Key": api_key, "Content-Type": "application/json"}
    logger.info("使用API KEY认证模式")
    logger.info(f"API主机: {api_host}")
    logger.info(f"API KEY: {api_key[:10]}...")
else:
    # 使用JWT认证（备用方案）
    JWT_EXPIRY_SECONDS = 900  # JWT令牌过期时间（15分钟）

    # 验证JWT认证所需的配置
    if not project_id or not key_id or (not private_key_path and not private_key_str):
        raise ValueError(
            "必须设置 HEFENG_API_KEY，或者设置完整的JWT认证配置（HEFENG_PROJECT_ID, HEFENG_KEY_ID, HEFENG_PRIVATE_KEY_PATH/HEFENG_PRIVATE_KEY）"
        )

    # 读取私钥
    private_key: bytes
    if private_key_path:
        try:
            with open(private_key_path, "rb") as f:
                private_key = f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"私钥文件未找到: {private_key_path}")
        except Exception as e:
            raise Exception(f"读取私钥文件失败: {e}")
    else:
        assert private_key_str is not None
        private_key = (
            private_key_str.replace("\\r\\n", "\n").replace("\\n", "\n").encode()
        )

    # 生成JWT令牌
    payload = {
        "iat": int(time.time()),
        "exp": int(time.time()) + JWT_EXPIRY_SECONDS,
        "sub": project_id,
    }
    headers = {"kid": key_id}

    try:
        encoded_jwt = jwt.encode(
            payload, private_key, algorithm="EdDSA", headers=headers
        )
    except Exception as e:
        raise Exception(f"JWT令牌生成失败: {e}")

    # 认证头
    auth_header = {
        "Authorization": f"Bearer {encoded_jwt}",
    }
    logger.info("使用JWT认证模式")
    logger.info(f"API主机: {api_host}")
    logger.info(f"项目ID: {project_id}")
    logger.info(f"密钥ID: {key_id}")


def _get_city_location(city: str, location: bool = False) -> Optional[str]:
    """
    根据城市名称获取LocationID

    Args:
        city: 城市名称，如 '北京'、'上海' 等

    Returns:
        LocationID字符串，如果查询失败则返回None

    Raises:
        无，所有异常都会被捕获并记录日志
    """
    url = f"https://{api_host}/geo/v2/city/lookup"

    try:
        response = httpx.get(url, headers=auth_header, params={"location": city})

        if response.status_code != 200:
            logger.error(
                f"查询城市位置失败 - 状态码: {response.status_code}, 响应: {response.text}"
            )
            return None

        data = response.json()
        if data and data.get("location") and len(data["location"]) > 0:
            location_id = data["location"][0]["id"]
            if location:
                # 如果需要返回经纬度信息
                lat_value = float(data["location"][0]["lat"])
                lon_value = float(data["location"][0]["lon"])
                formatted_lat = f"{lat_value:.2f}"
                formatted_lon = f"{lon_value:.2f}"

                location_lat_lon = formatted_lat + "," + formatted_lon
                logger.info(
                    f"成功获取城市 '{city}' 的经纬度: {location_lat_lon} (lat: {formatted_lat}, lon: {formatted_lon})"
                )

                return location_lat_lon
            logger.info(f"成功获取城市 '{city}' 的LocationID: {location_id}")
            return location_id
        else:
            logger.warning(f"未找到城市 '{city}' 的位置信息")
            return None

    except httpx.RequestError as e:
        logger.error(f"请求城市位置信息时发生网络错误: {e}")
        return None
    except Exception as e:
        logger.error(f"查询城市位置时发生未知错误: {e}")
        return None


@mcp.tool()
def get_weather(city: str, days: str = "3d") -> Optional[Dict[str, Any]]:
    """
    获取指定城市的天气预报

    提供详细的天气信息，包括温度、湿度、风力、降水等数据

    Args:
        city: 城市名称，支持中英文，如 '北京'、'上海'、'Beijing' 等
        days: 预报天数，支持 "3d"(默认)、"7d"、"10d"、"15d"、"30d"

    Returns:
        包含指定天数天气预报的JSON数据，如果查询失败则返回None
    """
    if not city or not city.strip():
        logger.error("城市名称不能为空")
        return None

    city = city.strip()

    # 验证days参数
    valid_days = ["3d", "7d", "10d", "15d", "30d"]
    if days not in valid_days:
        logger.error(f"无效的预报天数参数: {days}，支持的值: {', '.join(valid_days)}")
        return None

    # 获取城市LocationID
    location_id = _get_city_location(city)
    if not location_id:
        logger.error(f"无法获取城市 '{city}' 的位置信息")
        return None

    url = f"https://{api_host}/v7/weather/{days}?location={location_id}"

    try:
        response = httpx.get(url=url, headers=auth_header)

        if response.status_code != 200:
            logger.error(
                f"获取天气数据失败 - 状态码: {response.status_code}, 响应: {response.text}"
            )
            return None

        weather_data = response.json()
        logger.info(f"成功获取城市 '{city}' 的天气预报数据")
        return weather_data

    except httpx.RequestError as e:
        logger.error(f"请求天气数据时发生网络错误: {e}")
        return None
    except Exception as e:
        logger.error(f"获取天气数据时发生未知错误: {e}")
        return None


@mcp.tool()
def get_warning(city: str) -> Optional[Dict[str, Any]]:
    """
    获取指定城市的当前气象预警信息

    提供官方发布的各类气象灾害预警，包括台风、暴雨、高温、寒潮等预警信息

    Args:
        city: 城市名称，支持中英文，如 '北京'、'上海'、'Beijing' 等

    Returns:
        包含当前气象预警信息的JSON数据，如果查询失败则返回None

    Examples:
        >>> get_warning("北京")
        {
            "code": "200",
            "updateTime": "2023-07-20T14:30+08:00",
            "warning": [
                {
                    "id": "202307201430001",
                    "sender": "北京市气象台",
                    "title": "北京市气象台发布高温黄色预警",
                    "status": "active",
                    "level": "Yellow",
                    "type": "11B17",
                    "typeName": "高温",
                    ...
                }
            ]
        }
    """
    if not city or not city.strip():
        logger.error("城市名称不能为空")
        return None

    city = city.strip()
    lang = "zh"  # 使用中文语言

    # 获取城市LocationID
    location_id = _get_city_location(city)
    if not location_id:
        logger.error(f"无法获取城市 '{city}' 的位置信息")
        return None

    url = f"https://{api_host}/v7/warning/now?location={location_id}&lang={lang}"

    try:
        response = httpx.get(url, headers=auth_header)

        if response.status_code != 200:
            logger.error(
                f"获取预警数据失败 - 状态码: {response.status_code}, 响应: {response.text}"
            )
            return None

        warning_data = response.json()
        logger.info(f"成功获取城市 '{city}' 的气象预警数据")
        return warning_data

    except httpx.RequestError as e:
        logger.error(f"请求预警数据时发生网络错误: {e}")
        return None
    except Exception as e:
        logger.error(f"获取预警数据时发生未知错误: {e}")
        return None


@mcp.tool()
def get_indices(
    city: str,
    days: str = "1d",
    index_types: str = "1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16",
) -> Optional[Dict[str, Any]]:
    """
    获取指定城市的天气生活指数预报

    提供详细的生活指数信息，包括舒适度、洗车、穿衣、感冒、运动、旅游、紫外线等指数

    Args:
        city: 城市名称，支持中英文，如 '北京'、'上海'、'Beijing' 等
        days: 预报天数，支持 "1d"（1天）或 "3d"（3天），默认为 "1d"
        index_types: 生活指数类型ID，多个类型用英文逗号分隔默认获取所有指数
                    常用指数ID：
                    1-运动指数, 2-洗车指数, 3-穿衣指数, 4-感冒指数, 5-紫外线指数,
                    6-旅游指数, 7-花粉过敏指数, 8-舒适度指数, 9-交通指数, 10-防晒指数,
                    11-化妆指数, 12-空调开启指数, 13-晾晒指数, 14-钓鱼指数, 15-太阳镜指数,
                    16-空气污染扩散条件指数

    Returns:
        包含天气生活指数预报的JSON数据，如果查询失败则返回None
    """
    if not city or not city.strip():
        logger.error("城市名称不能为空")
        return None

    city = city.strip()

    # 验证days参数
    if days not in ["1d", "3d"]:
        logger.error(f"无效的预报天数参数: {days}，支持的值: 1d, 3d")
        return None

    # 验证index_types参数
    if not index_types or not index_types.strip():
        logger.error("指数类型参数不能为空")
        return None

    index_types = index_types.strip()

    # 获取城市LocationID
    location_id = _get_city_location(city)
    if not location_id:
        logger.error(f"无法获取城市 '{city}' 的位置信息")
        return None

    url = f"https://{api_host}/v7/indices/{days}"
    params = {"location": location_id, "type": index_types, "lang": "zh"}

    try:
        response = httpx.get(url, headers=auth_header, params=params)

        if response.status_code != 200:
            logger.error(
                f"获取生活指数数据失败 - 状态码: {response.status_code}, 响应: {response.text}"
            )
            return None

        indices_data = response.json()
        logger.info(f"成功获取城市 '{city}' 的生活指数预报数据")
        return indices_data

    except httpx.RequestError as e:
        logger.error(f"请求生活指数数据时发生网络错误: {e}")
        return None
    except Exception as e:
        logger.error(f"获取生活指数数据时发生未知错误: {e}")
        return None


@mcp.tool()
def get_air_quality(city: str) -> Optional[Dict[str, Any]]:
    """
    获取指定地点的实时空气质量数据

    提供精度为1x1公里的实时空气质量信息，包括AQI指数、污染物浓度、健康建议等

    Args:
        city: 城市名称，支持中英文，如 '北京'、'上海'、'Beijing' 等

    Returns:
        包含实时空气质量数据的JSON数据，如果查询失败则返回None
    """
    location_lat_lon = _get_city_location(city, location=True)
    if not location_lat_lon:
        logger.error(f"无法获取城市 '{city}' 的位置信息")
        return None

    # 分割经纬度
    try:
        lat, lon = location_lat_lon.split(",")
    except ValueError:
        logger.error(f"无法解析城市 '{city}' 的经纬度信息: {location_lat_lon}")
        return None

    url = f"https://{api_host}/airquality/v1/current/{lat}/{lon}"
    params = {"lang": "zh"}

    try:
        response = httpx.get(url, headers=auth_header, params=params)

        if response.status_code != 200:
            logger.error(
                f"获取空气质量数据失败 - 状态码: {response.status_code}, 响应: {response.text}"
            )
            return None

        air_quality_data = response.json()
        logger.info(f"成功获取城市 '{city}' 的空气质量数据")
        return air_quality_data

    except httpx.RequestError as e:
        logger.error(f"请求空气质量数据时发生网络错误: {e}")
        return None
    except Exception as e:
        logger.error(f"获取空气质量数据时发生未知错误: {e}")
        return None


@mcp.tool()
def get_air_quality_history(
    city: str, days: int = 10, lang: str = "zh"
) -> Optional[Dict[str, Any]]:
    """
    获取最近 N 天（最多10天，不包含今天）的空气质量历史再分析数据

    Args:
        city: 城市名称，支持中英文，如 '北京'、'上海'、'Beijing' 等
        days: 要获取的天数，必须在 1 到 10 之间（默认 10）
        lang: 多语言设置，默认中文 'zh'

    Returns:
        字典，键为 yyyyMMdd 日期，值为接口返回的 JSON 数据或错误信息；查询失败返回 None
    """
    if not city or not city.strip():
        logger.error("城市名称不能为空")
        return None

    if not isinstance(days, int) or days < 1 or days > 10:
        logger.error("参数 days 必须为整数，且范围为 1 到 10")
        return None

    city = city.strip()

    # 获取城市 LocationID（历史空气质量接口只支持 LocationID）
    location_id = _get_city_location(city)
    if not location_id:
        logger.error(f"无法获取城市 '{city}' 的位置信息")
        return None

    results: Dict[str, Any] = {}

    # 以北京时间为基准，生成从 today-days 到 yesterday 的日期列表
    # 使用时区感知的 UTC 时间以避免弃用警告
    beijing_now = datetime.now(tz=timezone.utc) + timedelta(hours=8)
    for offset in range(days, 0, -1):
        target_date = (beijing_now - timedelta(days=offset)).strftime("%Y%m%d")

        url = f"https://{api_host}/v7/historical/air"
        params = {"location": location_id, "date": target_date, "lang": lang}

        try:
            response = httpx.get(url, headers=auth_header, params=params)

            if response.status_code != 200:
                logger.error(
                    f"获取历史空气质量数据失败 ({target_date}) - 状态码: {response.status_code}, 响应: {response.text}"
                )
                results[target_date] = {
                    "error": response.text,
                    "status_code": response.status_code,
                }
            else:
                results[target_date] = response.json()

            # 小延迟以降低并发请求压力
            time.sleep(0.1)

        except httpx.RequestError as e:
            logger.error(f"请求历史空气质量数据时发生网络错误 ({target_date}): {e}")
            results[target_date] = {"error": str(e)}
        except Exception as e:
            logger.error(f"获取历史空气质量数据时发生未知错误 ({target_date}): {e}")
            results[target_date] = {"error": str(e)}

    logger.info(f"成功获取城市 '{city}' 的历史空气质量数据（最近 {days} 天）")
    return results


@mcp.tool()
def get_weather_history(
    *,
    location: Optional[str] = None,
    city: Optional[str] = None,
    days: int = 10,
    lang: str = "zh",
    unit: str = "m",
) -> Optional[Dict[str, Any]]:
    """
    获取最近 N 天（最多10天，不包含今天）的历史再分析天气数据（/v7/historical/weather）

    Notes:
        - 接口只支持 LocationID 查询（即必须先解析城市为 LocationID）
        - date 参数格式为 yyyyMMdd，例如 20251230
        - 最多只能查询最近 10 天（不包含今天），days 范围为 1 到 10

    Args:
        city: 城市名称，支持中英文，如 '北京'、'上海'、'Beijing' 等
        days: 要获取的天数，必须在 1 到 10 之间（默认 10）
        lang: 多语言设置，默认中文 'zh'
        unit: 单位，"m" 公制（默认）或 "i" 英制

    Returns:
        字典，键为 yyyyMMdd 日期，值为接口返回的 JSON 数据或错误信息；查询失败返回 None
    """
    # 接受 location（LocationID 或 "lon,lat"）或 city 两种方式之一
    if (not location or not str(location).strip()) and (not city or not city.strip()):
        logger.error("必须提供 location 或 city 其中之一")
        return None

    if not isinstance(days, int) or days < 1 or days > 10:
        logger.error("参数 days 必须为整数，且范围为 1 到 10")
        return None

    if unit not in {"m", "i"}:
        logger.error("无效的单位参数 unit: 应为 'm' 或 'i'")
        return None

    # 解析并准备 location_id（历史天气接口只支持 LocationID）
    location_id: Optional[str] = None

    loc_value = (
        location.strip() if isinstance(location, str) and location.strip() else None
    )
    if loc_value:
        # 如果传入的是经纬度（含逗号），尝试通过 Geo API 解析为 LocationID
        if "," in loc_value:
            resolved = _get_city_location(loc_value)
            if not resolved:
                logger.error(f"无法通过经纬度解析 LocationID: {loc_value}")
                return None
            location_id = resolved
        else:
            # 假定传入的是 LocationID（如 101010100），直接使用
            location_id = loc_value
    else:
        # 使用 city 名称解析 LocationID
        city = city.strip() if city else ""
        location_id = _get_city_location(city)
        if not location_id:
            logger.error(f"无法获取城市 '{city}' 的位置信息")
            return None

    results: Dict[str, Any] = {}

    # 以北京时间为基准，生成从 today-days 到 yesterday 的日期列表
    # 使用时区感知的 UTC 时间以避免弃用警告
    beijing_now = datetime.now(timezone.utc) + timedelta(hours=8)
    for offset in range(days, 0, -1):
        target_date = (beijing_now - timedelta(days=offset)).strftime("%Y%m%d")

        url = f"https://{api_host}/v7/historical/weather"
        params = {
            "location": location_id,
            "date": target_date,
            "lang": lang,
            "unit": unit,
        }

        try:
            response = httpx.get(url, headers=auth_header, params=params)

            if response.status_code != 200:
                logger.error(
                    f"获取历史天气数据失败 ({target_date}) - 状态码: {response.status_code}, 响应: {response.text}"
                )
                results[target_date] = {
                    "error": response.text,
                    "status_code": response.status_code,
                }
            else:
                results[target_date] = response.json()

            # 小延迟以降低并发请求压力
            time.sleep(0.1)

        except httpx.RequestError as e:
            logger.error(f"请求历史天气数据时发生网络错误 ({target_date}): {e}")
            results[target_date] = {"error": str(e)}
        except Exception as e:
            logger.error(f"获取历史天气数据时发生未知错误 ({target_date}): {e}")
            results[target_date] = {"error": str(e)}

    logger.info(f"成功获取城市 '{city}' 的历史天气数据（最近 {days} 天）")
    return results


@mcp.tool()
def get_hourly_weather(
    hours: str = "24h",
    location: Optional[str] = None,
    city: Optional[str] = None,
    lang: str = "zh",
    unit: str = "m",
) -> Optional[Dict[str, Any]]:
    """
    获取指定地点未来 24-168 小时的逐小时天气预报

    支持三种时长：24h、72h、168h可通过 LocationID 或 "lon,lat" 坐标，或传入城市名（自动解析 LocationID）

    Args:
        hours: 预报小时数，支持 "24h"、"72h"、"168h"，默认 "24h"
        location: 位置标识，支持 LocationID 或 "经度,纬度"（小数点后最多两位）
        city: 城市名称（当未提供 location 时使用此参数自动解析 LocationID）
        lang: 多语言代码，默认 "zh"
        unit: 单位，"m" 公制（默认）或 "i" 英制

    Returns:
        包含逐小时天气预报的 JSON 数据，如果失败返回 None
    """
    # 校验 hours 参数
    valid_hours = {"24h", "72h", "168h"}
    if hours not in valid_hours:
        logger.error(
            f"无效的 hours 参数: {hours}，支持的值: {', '.join(sorted(valid_hours))}"
        )
        return None

    # 校验 unit 参数
    if unit not in {"m", "i"}:
        logger.error(f"无效的单位参数 unit: {unit}，支持的值: m, i")
        return None

    # 准备 location 值
    loc_value: Optional[str] = location.strip() if isinstance(location, str) else None
    if not loc_value:
        if not city or not city.strip():
            logger.error("必须提供 location 或 city 其中之一")
            return None
        # 通过城市名解析 LocationID
        loc_value = _get_city_location(city.strip())
        if not loc_value:
            logger.error(f"无法获取城市 '{city}' 的位置信息")
            return None

    url = f"https://{api_host}/v7/weather/{hours}"
    params = {"location": loc_value, "lang": lang, "unit": unit}

    try:
        response = httpx.get(url, headers=auth_header, params=params)

        if response.status_code != 200:
            logger.error(
                f"获取逐小时天气数据失败 - 状态码: {response.status_code}, 响应: {response.text}"
            )
            return None

        hourly_data = response.json()
        who = city or loc_value
        logger.info(f"成功获取 '{who}' 的逐小时天气预报数据（{hours}）")
        return hourly_data

    except httpx.RequestError as e:
        logger.error(f"请求逐小时天气数据时发生网络错误: {e}")
        return None
    except Exception as e:
        logger.error(f"获取逐小时天气数据时发生未知错误: {e}")
        return None


@mcp.tool()
def get_weather_now(
    location: Optional[str] = None,
    city: Optional[str] = None,
    lang: str = "zh",
    unit: str = "m",
) -> Optional[Dict[str, Any]]:
    """
    获取实时（近实时）天气数据（/v7/weather/now）

    包含实时温度、体感温度、风力风向、相对湿度、大气压强、降水量、能见度、露点温度、云量等
    注意：实况数据通常较真实时间有 5-20 分钟延迟，请以返回数据中的 obsTime 为准

    Args:
        location: 地区 LocationID 或 "经度,纬度"（十进制，最多两位小数）
        city: 城市名称（当未提供 location 时使用此参数自动解析 LocationID）
        lang: 多语言代码，默认 "zh"
        unit: 单位，"m" 公制（默认）或 "i" 英制

    Returns:
        包含实况天气的 JSON 数据，如果失败返回 None
    """
    # 校验 unit 参数
    if unit not in {"m", "i"}:
        logger.error(f"无效的单位参数 unit: {unit}，支持的值: m, i")
        return None

    # 准备 location 值
    loc_value: Optional[str] = location.strip() if isinstance(location, str) else None
    if not loc_value:
        if not city or not city.strip():
            logger.error("必须提供 location 或 city 其中之一")
            return None
        # 通过城市名解析 LocationID
        loc_value = _get_city_location(city.strip())
        if not loc_value:
            logger.error(f"无法获取城市 '{city}' 的位置信息")
            return None

    url = f"https://{api_host}/v7/weather/now"
    params = {"location": loc_value, "lang": lang, "unit": unit}

    try:
        response = httpx.get(url, headers=auth_header, params=params)
        if response.status_code != 200:
            logger.error(
                f"获取实况天气数据失败 - 状态码: {response.status_code}, 响应: {response.text}"
            )
            return None

        now_data = response.json()
        who = city or loc_value
        logger.info(f"成功获取 '{who}' 的实况天气数据")
        return now_data

    except httpx.RequestError as e:
        logger.error(f"请求实况天气数据时发生网络错误: {e}")
        return None
    except Exception as e:
        logger.error(f"获取实况天气数据时发生未知错误: {e}")
        return None


@mcp.tool()
def get_minutely_5m(location: str, lang: str = "zh") -> Optional[Dict[str, Any]]:
    """
    获取分钟级降水（近两小时、每5分钟）预报数据

    平台: API iOS Android

    请求路径: /v7/minutely/5m

    Args:
        location: 必选，查询地区的经度,纬度（十进制，最多支持小数点后两位），例如 "116.38,39.91"。
                  也支持传入城市名（会尝试解析为经纬度）。
        lang: 可选，多语言设置，默认中文 'zh'

    Returns:
        接口返回的 JSON 数据，失败时返回 None
    """
    if not location or not str(location).strip():
        logger.error("location 参数不能为空，需为经度,纬度（如 116.38,39.91）或城市名")
        return None

    loc_value = str(location).strip()

    # 如果传入的不是经纬度（不包含逗号），尝试当作城市名解析为经纬度
    if "," not in loc_value:
        resolved = _get_city_location(loc_value, location=True)
        if not resolved:
            logger.error(f"无法将 '{loc_value}' 解析为经纬度")
            return None
        loc_value = resolved

    url = f"https://{api_host}/v7/minutely/5m"
    params = {"location": loc_value, "lang": lang}

    try:
        response = httpx.get(url, headers=auth_header, params=params)

        if response.status_code != 200:
            logger.error(
                f"获取分钟级降水数据失败 - 状态码: {response.status_code}, 响应: {response.text}"
            )
            return None

        minutely_data = response.json()
        logger.info(f"成功获取 location={loc_value} 的分钟级降水预报数据")
        return minutely_data

    except httpx.RequestError as e:
        logger.error(f"请求分钟级降水数据时发生网络错误: {e}")
        return None
    except Exception as e:
        logger.error(f"获取分钟级降水数据时发生未知错误: {e}")
        return None


@mcp.tool()
def get_astronomy_moon(
    location: str, date: str, lang: str = "zh"
) -> Optional[Dict[str, Any]]:
    """
    获取未来60天内的月升月落和逐小时月相数据（全球城市）

    请求路径: /v7/astronomy/moon

    Args:
        location: 必选，LocationID 或 经度,纬度（十进制，最多两位小数），示例: "101010100" 或 "116.41,39.92"。
                  也支持传入城市名，会尝试解析为 LocationID。
        date: 必选，选择日期，格式 yyyyMMdd，支持今天到未来60天（包含今天）
        lang: 可选，多语言设置，默认中文 'zh'

    Returns:
        接口返回的 JSON 数据，失败时返回 None
    """
    if not location or not str(location).strip():
        logger.error(
            "location 参数不能为空，需为 LocationID 或 经度,纬度（如 116.41,39.92）或城市名"
        )
        return None

    loc_value = str(location).strip()

    # 如果为经纬度，格式化为两位小数
    if "," in loc_value:
        try:
            lon_str, lat_str = [s.strip() for s in loc_value.split(",", 1)]
            lon = float(lon_str)
            lat = float(lat_str)
            loc_value = f"{lon:.2f},{lat:.2f}"
        except Exception:
            logger.error(f"无法解析经纬度参数: {loc_value}, 期望格式 lon,lat")
            return None
    else:
        # 如果看起来像 LocationID（全数字），直接使用，否则尝试解析为 LocationID
        if not loc_value.isdigit():
            resolved = _get_city_location(loc_value)
            if not resolved:
                logger.error(f"无法将 '{loc_value}' 解析为 LocationID")
                return None
            loc_value = resolved

    # 验证 date 格式并在允许范围内（今天 ~ 今天+60天）
    try:
        target_date = datetime.strptime(date, "%Y%m%d").date()
    except Exception:
        logger.error("date 参数格式错误，需为 yyyyMMdd，例如 20211120")
        return None

    beijing_today = (datetime.now(timezone.utc) + timedelta(hours=8)).date()
    max_date = beijing_today + timedelta(days=60)
    if target_date < beijing_today or target_date > max_date:
        logger.error(
            f"date 参数超出允许范围：应在 {beijing_today.strftime('%Y%m%d')} 到 {max_date.strftime('%Y%m%d')} 之间"
        )
        return None

    url = f"https://{api_host}/v7/astronomy/moon"
    params = {"location": loc_value, "date": date, "lang": lang}

    try:
        response = httpx.get(url, headers=auth_header, params=params)

        if response.status_code != 200:
            logger.error(
                f"获取月亮天文数据失败 - 状态码: {response.status_code}, 响应: {response.text}"
            )
            return None

        moon_data = response.json()
        logger.info(f"成功获取 location={loc_value} date={date} 的月亮天文数据")
        return moon_data

    except httpx.RequestError as e:
        logger.error(f"请求月亮天文数据时发生网络错误: {e}")
        return None
    except Exception as e:
        logger.error(f"获取月亮天文数据时发生未知错误: {e}")
        return None


@mcp.tool()
def get_astronomy_sun(
    location: str, date: str, lang: str = "zh"
) -> Optional[Dict[str, Any]]:
    """
    获取未来60天内的日出日落时间（全球任意地点）

    请求路径: /v7/astronomy/sun

    Args:
        location: 必选，LocationID 或 经度,纬度（十进制，最多两位小数），示例: "101010100" 或 "116.41,39.92"。
                  也支持传入城市名，会尝试解析为 LocationID。
        date: 必选，选择日期，格式 yyyyMMdd，支持今天到未来60天（包含今天）
        lang: 可选，多语言设置，默认中文 'zh'

    Returns:
        接口返回的 JSON 数据，失败时返回 None
    """
    if not location or not str(location).strip():
        logger.error(
            "location 参数不能为空，需为 LocationID 或 经度,纬度（如 116.41,39.92）或城市名"
        )
        return None

    loc_value = str(location).strip()

    # 如果为经纬度，格式化为两位小数
    if "," in loc_value:
        try:
            lon_str, lat_str = [s.strip() for s in loc_value.split(",", 1)]
            lon = float(lon_str)
            lat = float(lat_str)
            loc_value = f"{lon:.2f},{lat:.2f}"
        except Exception:
            logger.error(f"无法解析经纬度参数: {loc_value}, 期望格式 lon,lat")
            return None
    else:
        # 如果看起来像 LocationID（全数字），直接使用，否则尝试解析为 LocationID
        if not loc_value.isdigit():
            resolved = _get_city_location(loc_value)
            if not resolved:
                logger.error(f"无法将 '{loc_value}' 解析为 LocationID")
                return None
            loc_value = resolved

    # 验证 date 格式并在允许范围内（今天 ~ 今天+60天）
    try:
        target_date = datetime.strptime(date, "%Y%m%d").date()
    except Exception:
        logger.error("date 参数格式错误，需为 yyyyMMdd，例如 20210220")
        return None

    beijing_today = (datetime.now(timezone.utc) + timedelta(hours=8)).date()
    max_date = beijing_today + timedelta(days=60)
    if target_date < beijing_today or target_date > max_date:
        logger.error(
            f"date 参数超出允许范围：应在 {beijing_today.strftime('%Y%m%d')} 到 {max_date.strftime('%Y%m%d')} 之间"
        )
        return None

    url = f"https://{api_host}/v7/astronomy/sun"
    params = {"location": loc_value, "date": date, "lang": lang}

    try:
        response = httpx.get(url, headers=auth_header, params=params)

        if response.status_code != 200:
            logger.error(
                f"获取太阳天文数据失败 - 状态码: {response.status_code}, 响应: {response.text}"
            )
            return None

        sun_data = response.json()
        logger.info(f"成功获取 location={loc_value} date={date} 的太阳天文数据")
        return sun_data

    except httpx.RequestError as e:
        logger.error(f"请求太阳天文数据时发生网络错误: {e}")
        return None
    except Exception as e:
        logger.error(f"获取太阳天文数据时发生未知错误: {e}")
        return None


@mcp.tool()
def get_grid_weather_now(
    location: str, lang: str = "zh", unit: str = "m"
) -> Optional[Dict[str, Any]]:
    """
    获取全球指定坐标的格点实时天气数据（高分辨率数值模式）

    基于数值预报模型提供3-5公里分辨率的实时天气，适合精确坐标查询。
    注意：格点天气采用UTC 0时区表示时间，基于数值模型而非观测站数据。

    Args:
        location: 必选，经度,纬度坐标（十进制，最多两位小数），例如 "116.41,39.92"
        lang: 可选，多语言设置，默认中文 "zh"
        unit: 可选，数据单位，"m" 公制（默认）或 "i" 英制

    Returns:
        包含格点实时天气的 JSON 数据，如果失败返回 None

    Examples:
        >>> get_grid_weather_now("116.41,39.92")
        {
            "code": "200",
            "updateTime": "2021-12-16T18:25+08:00",
            "fxLink": "https://www.qweather.com",
            "now": {
                "obsTime": "2021-12-16T10:00+00:00",
                "temp": "-1",
                "icon": "150",
                "text": "晴",
                "wind360": "287",
                "windDir": "西北风",
                "windScale": "2",
                "windSpeed": "10",
                "humidity": "27",
                "precip": "0.0",
                "pressure": "1021",
                "cloud": "0",
                "dew": "-17"
            },
            "refer": {
                "sources": ["QWeather"],
                "license": ["QWeather Developers License"]
            }
        }
    """
    # 验证 location 参数格式（必须是经纬度坐标）
    if not location or not str(location).strip():
        logger.error("location 参数不能为空，需为经度,纬度坐标（如 116.41,39.92）")
        return None

    loc_value = str(location).strip()

    # 验证坐标格式
    if "," not in loc_value:
        logger.error(
            f"location 参数格式错误：'{loc_value}'，期望格式：经度,纬度（如 116.41,39.92）"
        )
        return None

    try:
        # 解析并验证经纬度坐标
        lon_str, lat_str = [s.strip() for s in loc_value.split(",", 1)]
        lon = float(lon_str)
        lat = float(lat_str)

        # 验证经纬度范围
        if not (-180 <= lon <= 180):
            logger.error(f"经度超出有效范围 [-180, 180]：{lon}")
            return None
        if not (-90 <= lat <= 90):
            logger.error(f"纬度超出有效范围 [-90, 90]：{lat}")
            return None

        # 格式化坐标为两位小数
        formatted_loc = f"{lon:.2f},{lat:.2f}"
        logger.info(f"格式化坐标：{loc_value} → {formatted_loc}")

    except Exception as e:
        logger.error(f"无法解析坐标参数：{loc_value}，错误：{e}")
        return None

    # 验证 unit 参数
    if unit not in {"m", "i"}:
        logger.error(f"无效的单位参数 unit: {unit}，支持的值: m, i")
        return None

    url = f"https://{api_host}/v7/grid-weather/now"
    params = {"location": formatted_loc, "lang": lang, "unit": unit}

    try:
        response = httpx.get(url, headers=auth_header, params=params)

        if response.status_code != 200:
            logger.error(
                f"获取格点实时天气数据失败 - 状态码: {response.status_code}, 响应: {response.text}"
            )
            return None

        grid_weather_data = response.json()
        logger.info(f"成功获取坐标 {formatted_loc} 的格点实时天气数据")
        return grid_weather_data

    except httpx.RequestError as e:
        logger.error(f"请求格点实时天气数据时发生网络错误: {e}")
        return None
    except Exception as e:
        logger.error(f"获取格点实时天气数据时发生未知错误: {e}")
        return None


@mcp.tool()
def get_grid_weather_daily(
    location: str, days: str = "3d", lang: str = "zh", unit: str = "m"
) -> Optional[Dict[str, Any]]:
    """
    获取全球指定坐标的格点每日天气预报（高分辨率数值模式）

    基于数值预报模型提供3-5公里分辨率的每日天气预报，支持3天或7天预报。
    注意：格点天气采用UTC 0时区表示时间，基于数值模型而非观测站数据。

    Args:
        location: 必选，经度,纬度坐标（十进制，最多两位小数），例如 "116.41,39.92"
        days: 可选，预报天数，"3d"（3天，默认）或 "7d"（7天）
        lang: 可选，多语言设置，默认中文 "zh"
        unit: 可选，数据单位，"m" 公制（默认）或 "i" 英制

    Returns:
        包含格点每日天气预报的 JSON 数据，如果失败返回 None

    Examples:
        >>> get_grid_weather_daily("116.41,39.92")
        {
            "code": "200",
            "updateTime": "2021-12-16T18:30+08:00",
            "fxLink": "https://www.qweather.com",
            "daily": [
                {
                    "fxDate": "2021-12-16",
                    "tempMax": "2",
                    "tempMin": "-7",
                    "iconDay": "104",
                    "iconNight": "154",
                    "textDay": "阴",
                    "textNight": "阴",
                    "wind360Day": "344",
                    "windDirDay": "西北风",
                    "windScaleDay": "4-5",
                    "windSpeedDay": "9",
                    "wind360Night": "304",
                    "windDirNight": "西北风",
                    "windScaleNight": "4-5",
                    "windSpeedNight": "6",
                    "humidity": "36",
                    "precip": "0.0",
                    "pressure": "1026"
                },
                ...
            ],
            "refer": {
                "sources": ["QWeather"],
                "license": ["QWeather Developers License"]
            }
        }
    """
    # 验证 location 参数格式（必须是经纬度坐标）
    if not location or not str(location).strip():
        logger.error("location 参数不能为空，需为经度,纬度坐标（如 116.41,39.92）")
        return None

    loc_value = str(location).strip()

    # 验证坐标格式
    if "," not in loc_value:
        logger.error(
            f"location 参数格式错误：'{loc_value}'，期望格式：经度,纬度（如 116.41,39.92）"
        )
        return None

    try:
        # 解析并验证经纬度坐标
        lon_str, lat_str = [s.strip() for s in loc_value.split(",", 1)]
        lon = float(lon_str)
        lat = float(lat_str)

        # 验证经纬度范围
        if not (-180 <= lon <= 180):
            logger.error(f"经度超出有效范围 [-180, 180]：{lon}")
            return None
        if not (-90 <= lat <= 90):
            logger.error(f"纬度超出有效范围 [-90, 90]：{lat}")
            return None

        # 格式化坐标为两位小数
        formatted_loc = f"{lon:.2f},{lat:.2f}"
        logger.info(f"格式化坐标：{loc_value} → {formatted_loc}")

    except Exception as e:
        logger.error(f"无法解析坐标参数：{loc_value}，错误：{e}")
        return None

    # 验证 days 参数
    valid_days = ["3d", "7d"]
    if days not in valid_days:
        logger.error(f"无效的预报天数参数: {days}，支持的值: {', '.join(valid_days)}")
        return None

    # 验证 unit 参数
    if unit not in {"m", "i"}:
        logger.error(f"无效的单位参数 unit: {unit}，支持的值: m, i")
        return None

    url = f"https://{api_host}/v7/grid-weather/{days}"
    params = {"location": formatted_loc, "lang": lang, "unit": unit}

    try:
        response = httpx.get(url, headers=auth_header, params=params)

        if response.status_code != 200:
            logger.error(
                f"获取格点每日天气预报失败 - 状态码: {response.status_code}, 响应: {response.text}"
            )
            return None

        grid_daily_data = response.json()
        logger.info(f"成功获取坐标 {formatted_loc} 的格点每日天气预报数据（{days}）")
        return grid_daily_data

    except httpx.RequestError as e:
        logger.error(f"请求格点每日天气预报时发生网络错误: {e}")
        return None
    except Exception as e:
        logger.error(f"获取格点每日天气预报时发生未知错误: {e}")
        return None


@mcp.tool()
def get_grid_weather_hourly(
    location: str, hours: str = "24h", lang: str = "zh", unit: str = "m"
) -> Optional[Dict[str, Any]]:
    """
    获取全球指定坐标的格点逐小时天气预报（高分辨率数值模式）

    基于数值预报模型提供3-5公里分辨率的逐小时天气预报，支持24小时或72小时预报。
    注意：格点天气采用UTC 0时区表示时间，基于数值模型而非观测站数据。

    Args:
        location: 必选，经度,纬度坐标（十进制，最多两位小数），例如 "116.41,39.92"
        hours: 可选，预报小时数，"24h"（24小时，默认）或 "72h"（72小时）
        lang: 可选，多语言设置，默认中文 "zh"
        unit: 可选，数据单位，"m" 公制（默认）或 "i" 英制

    Returns:
        包含格点逐小时天气预报的 JSON 数据，如果失败返回 None

    Examples:
        >>> get_grid_weather_hourly("116.41,39.92")
        {
            "code": "200",
            "updateTime": "2021-12-16T19:27+08:00",
            "fxLink": "https://www.qweather.com",
            "hourly": [
                {
                    "fxTime": "2021-12-16T12:00+00:00",
                    "temp": "-2",
                    "icon": "150",
                    "text": "晴",
                    "wind360": "285",
                    "windDir": "西北风",
                    "windScale": "2",
                    "windSpeed": "8",
                    "humidity": "30",
                    "precip": "0.0",
                    "pressure": "1022",
                    "cloud": "0",
                    "dew": "-17"
                },
                ...
            ],
            "refer": {
                "sources": ["QWeather"],
                "license": ["QWeather Developers License"]
            }
        }
    """
    # 验证 location 参数格式（必须是经纬度坐标）
    if not location or not str(location).strip():
        logger.error("location 参数不能为空，需为经度,纬度坐标（如 116.41,39.92）")
        return None

    loc_value = str(location).strip()

    # 验证坐标格式
    if "," not in loc_value:
        logger.error(
            f"location 参数格式错误：'{loc_value}'，期望格式：经度,纬度（如 116.41,39.92）"
        )
        return None

    try:
        # 解析并验证经纬度坐标
        lon_str, lat_str = [s.strip() for s in loc_value.split(",", 1)]
        lon = float(lon_str)
        lat = float(lat_str)

        # 验证经纬度范围
        if not (-180 <= lon <= 180):
            logger.error(f"经度超出有效范围 [-180, 180]：{lon}")
            return None
        if not (-90 <= lat <= 90):
            logger.error(f"纬度超出有效范围 [-90, 90]：{lat}")
            return None

        # 格式化坐标为两位小数
        formatted_loc = f"{lon:.2f},{lat:.2f}"
        logger.info(f"格式化坐标：{loc_value} → {formatted_loc}")

    except Exception as e:
        logger.error(f"无法解析坐标参数：{loc_value}，错误：{e}")
        return None

    # 验证 hours 参数
    valid_hours = ["24h", "72h"]
    if hours not in valid_hours:
        logger.error(
            f"无效的预报小时数参数: {hours}，支持的值: {', '.join(valid_hours)}"
        )
        return None

    # 验证 unit 参数
    if unit not in {"m", "i"}:
        logger.error(f"无效的单位参数 unit: {unit}，支持的值: m, i")
        return None

    url = f"https://{api_host}/v7/grid-weather/{hours}"
    params = {"location": formatted_loc, "lang": lang, "unit": unit}

    try:
        response = httpx.get(url, headers=auth_header, params=params)

        if response.status_code != 200:
            logger.error(
                f"获取格点逐小时天气预报失败 - 状态码: {response.status_code}, 响应: {response.text}"
            )
            return None

        grid_hourly_data = response.json()
        logger.info(f"成功获取坐标 {formatted_loc} 的格点逐小时天气预报数据（{hours}）")
        return grid_hourly_data

    except httpx.RequestError as e:
        logger.error(f"请求格点逐小时天气预报时发生网络错误: {e}")
        return None
    except Exception as e:
        logger.error(f"获取格点逐小时天气预报时发生未知错误: {e}")
        return None


@mcp.tool()
def get_air_quality_hourly(
    location: str, hours: str = "24h", lang: str = "zh"
) -> Optional[Dict[str, Any]]:
    """
    获取指定地点未来24-168小时的逐小时空气质量预报数据

    提供精度为1x1公里的逐小时空气质量预报，包括AQI、污染物浓度等详细信息

    Args:
        location: 必选，经纬度坐标（十进制，最多两位小数），格式: "纬度,经度"，如 "39.92,116.41"
                  注意顺序是纬度在前，经度在后
        hours: 可选，预报小时数，支持 "24h"（24小时，默认）、"72h"（72小时）、"168h"（168小时）
        lang: 可选，多语言设置，默认中文 "zh"

    Returns:
        包含逐小时空气质量预报的 JSON 数据，如果失败返回 None

    Examples:
        >>> get_air_quality_hourly("39.92,116.41", "24h")
        {
            "code": "200",
            "updateTime": "2023-07-20T14:30+08:00",
            "hourly": [
                {
                    "fxTime": "2023-07-20T15:00+08:00",
                    "aqi": "75",
                    "level": "2",
                    "category": "良",
                    "primary": "pm10",
                    "pm10": "105",
                    "pm2p5": "55",
                    "no2": "42",
                    "so2": "8",
                    "co": "0.6",
                    "o3": "120"
                },
                ...
            ],
            "refer": {
                "sources": ["QWeather"],
                "license": ["QWeather Developers License"]
            }
        }
    """
    if not location or not str(location).strip():
        logger.error("location 参数不能为空，需为纬度,经度坐标（如 39.92,116.41）")
        return None

    loc_value = str(location).strip()

    # 验证坐标格式（必须是 "纬度,经度" 格式）
    if "," not in loc_value:
        logger.error(
            f"location 参数格式错误：'{loc_value}'，期望格式：纬度,经度（如 39.92,116.41）"
        )
        return None

    try:
        # 解析并验证经纬度坐标
        lat_str, lon_str = [s.strip() for s in loc_value.split(",", 1)]
        lat = float(lat_str)
        lon = float(lon_str)

        # 验证经纬度范围
        if not (-90 <= lat <= 90):
            logger.error(f"纬度超出有效范围 [-90, 90]：{lat}")
            return None
        if not (-180 <= lon <= 180):
            logger.error(f"经度超出有效范围 [-180, 180]：{lon}")
            return None

        # 格式化坐标为两位小数
        formatted_loc = f"{lat:.2f},{lon:.2f}"
        logger.info(f"格式化坐标：{loc_value} → {formatted_loc}")

    except Exception as e:
        logger.error(f"无法解析坐标参数：{loc_value}，错误：{e}")
        return None

    # 验证 hours 参数
    valid_hours = {"24h", "72h", "168h"}
    if hours not in valid_hours:
        logger.error(
            f"无效的预报小时数参数: {hours}，支持的值: {', '.join(sorted(valid_hours))}"
        )
        return None

    # API端点格式: /airquality/v1/hourly/{latitude}/{longitude}
    lat, lon = formatted_loc.split(",")
    url = f"https://{api_host}/airquality/v1/hourly/{lat}/{lon}"
    params = {"hours": hours, "lang": lang}

    try:
        response = httpx.get(url, headers=auth_header, params=params)

        if response.status_code != 200:
            logger.error(
                f"获取空气质量小时预报数据失败 - 状态码: {response.status_code}, 响应: {response.text}"
            )
            return None

        air_hourly_data = response.json()
        logger.info(f"成功获取坐标 {formatted_loc} 的空气质量小时预报数据（{hours}）")
        return air_hourly_data

    except httpx.RequestError as e:
        logger.error(f"请求空气质量小时预报数据时发生网络错误: {e}")
        return None
    except Exception as e:
        logger.error(f"获取空气质量小时预报数据时发生未知错误: {e}")
        return None


@mcp.tool()
def get_air_quality_daily(
    location: str, days: str = "3d", lang: str = "zh"
) -> Optional[Dict[str, Any]]:
    """
    获取指定地点未来最多15天的逐日空气质量预报数据

    提供精度为1x1公里的逐日空气质量预报，包括AQI、污染物浓度、主要污染物等信息

    Args:
        location: 必选，经纬度坐标（十进制，最多两位小数），格式: "纬度,经度"，如 "39.92,116.41"
                  注意顺序是纬度在前，经度在后
        days: 可选，预报天数，支持 "3d"（3天，默认）、"7d"（7天）、"15d"（15天）
        lang: 可选，多语言设置，默认中文 "zh"

    Returns:
        包含逐日空气质量预报的 JSON 数据，如果失败返回 None

    Examples:
        >>> get_air_quality_daily("39.92,116.41", "7d")
        {
            "code": "200",
            "updateTime": "2023-07-20T14:30+08:00",
            "daily": [
                {
                    "fxDate": "2023-07-20",
                    "aqi": "75",
                    "level": "2",
                    "category": "良",
                    "primary": "pm10",
                    "pm10": "105",
                    "pm2p5": "55",
                    "no2": "42",
                    "so2": "8",
                    "co": "0.6",
                    "o3": "120"
                },
                ...
            ],
            "refer": {
                "sources": ["QWeather"],
                "license": ["QWeather Developers License"]
            }
        }
    """
    if not location or not str(location).strip():
        logger.error("location 参数不能为空，需为纬度,经度坐标（如 39.92,116.41）")
        return None

    loc_value = str(location).strip()

    # 验证坐标格式（必须是 "纬度,经度" 格式）
    if "," not in loc_value:
        logger.error(
            f"location 参数格式错误：'{loc_value}'，期望格式：纬度,经度（如 39.92,116.41）"
        )
        return None

    try:
        # 解析并验证经纬度坐标
        lat_str, lon_str = [s.strip() for s in loc_value.split(",", 1)]
        lat = float(lat_str)
        lon = float(lon_str)

        # 验证经纬度范围
        if not (-90 <= lat <= 90):
            logger.error(f"纬度超出有效范围 [-90, 90]：{lat}")
            return None
        if not (-180 <= lon <= 180):
            logger.error(f"经度超出有效范围 [-180, 180]：{lon}")
            return None

        # 格式化坐标为两位小数
        formatted_loc = f"{lat:.2f},{lon:.2f}"
        logger.info(f"格式化坐标：{loc_value} → {formatted_loc}")

    except Exception as e:
        logger.error(f"无法解析坐标参数：{loc_value}，错误：{e}")
        return None

    # 验证 days 参数
    valid_days = {"3d", "7d", "15d"}
    if days not in valid_days:
        logger.error(f"无效的预报天数参数: {days}，支持的值: {', '.join(sorted(valid_days))}")
        return None

    # API端点格式: /airquality/v1/daily/{latitude}/{longitude}
    lat, lon = formatted_loc.split(",")
    url = f"https://{api_host}/airquality/v1/daily/{lat}/{lon}"
    params = {"days": days, "lang": lang}

    try:
        response = httpx.get(url, headers=auth_header, params=params)

        if response.status_code != 200:
            logger.error(
                f"获取空气质量每日预报数据失败 - 状态码: {response.status_code}, 响应: {response.text}"
            )
            return None

        air_daily_data = response.json()
        logger.info(f"成功获取坐标 {formatted_loc} 的空气质量每日预报数据（{days}）")
        return air_daily_data

    except httpx.RequestError as e:
        logger.error(f"请求空气质量每日预报数据时发生网络错误: {e}")
        return None
    except Exception as e:
        logger.error(f"获取空气质量每日预报数据时发生未知错误: {e}")
        return None


@mcp.tool()
def get_air_quality_stations(
    station_id: str, lang: str = "zh"
) -> Optional[Dict[str, Any]]:
    """
    获取指定空气质量监测站的污染物浓度数据

    提供各个国家或地区监测站的污染物浓度值，监测站ID需要通过其他方式获取

    Args:
        station_id: 必选，空气质量监测站的ID，格式如 "P58911"、"P53763" 等
                   注意：这是监测站的专用ID，不是城市的LocationID
        lang: 可选，多语言设置，默认中文 "zh"

    Returns:
        包含监测站污染物数据的 JSON 数据，如果失败返回 None

    Examples:
        >>> get_air_quality_stations("P58911")
        {
            "metadata": {
                "tag": "airquality/v1/station",
                "sources": ["QWeather"]
            },
            "pollutants": [
                {
                    "code": "co",
                    "name": "一氧化碳",
                    "fullName": "Carbon Monoxide",
                    "concentration": {
                        "value": "0.6",
                        "unit": "mg/m³"
                    }
                }
            ]
        }
    """
    if not station_id or not str(station_id).strip():
        logger.error("station_id 参数不能为空，需为空气质量监测站ID（如 P58911）")
        return None

    station_value = str(station_id).strip()

    # 验证监测站ID格式（应该以P开头，后跟数字）
    if not station_value.startswith('P') or not station_value[1:].isdigit():
        logger.error(f"监测站ID格式可能不正确: {station_value}，期望格式: P58911")
        # 这里不返回None，因为可能有其他格式的监测站ID

    # 根据官方文档，API端点格式: /airquality/v1/station/{station_id}
    url = f"https://{api_host}/airquality/v1/station/{station_value}"
    params = {"lang": lang}

    try:
        response = httpx.get(url, headers=auth_header, params=params)

        if response.status_code != 200:
            logger.error(
                f"获取空气质量监测站数据失败 - 状态码: {response.status_code}, 响应: {response.text}"
            )
            return None

        stations_data = response.json()
        logger.info(f"成功获取监测站 '{station_value}' 的污染物浓度数据")
        return stations_data

    except httpx.RequestError as e:
        logger.error(f"请求空气质量监测站数据时发生网络错误: {e}")
        return None
    except Exception as e:
        logger.error(f"获取空气质量监测站数据时发生未知错误: {e}")
        return None


@mcp.tool()
def get_top_cities(
    number: int = 10, city_type: str = "cn", lang: str = "zh"
) -> Optional[Dict[str, Any]]:
    """
    获取和风天气提供的热门城市列表

    提供快速访问常用城市的功能，支持不同区域的热门城市查询

    Args:
        number: 可选，返回结果的数量，默认10，建议范围1-50
        city_type: 可选，返回城市类型，支持：
                   - "cn": 中国热门城市（默认）
                   - "world": 世界热门城市
                   - "overseas": 海外热门城市
        lang: 可选，多语言设置，默认中文 "zh"

    Returns:
        包含热门城市列表的 JSON 数据，如果失败返回 None

    Examples:
        >>> get_top_cities(10, "cn")
        {
            "code": "200",
            "topCity": [
                {
                    "id": "101010100",
                    "name": "北京",
                    "country": "CN",
                    "path": "北京,北京,中国",
                    "timezone": "Asia/Shanghai",
                    "timezoneOffset": "+08:00"
                },
                {
                    "id": "101020100",
                    "name": "上海",
                    "country": "CN",
                    "path": "上海,上海,中国",
                    "timezone": "Asia/Shanghai",
                    "timezoneOffset": "+08:00"
                },
                ...
            ]
        }
    """
    # 验证 number 参数
    if not isinstance(number, int) or number < 1 or number > 100:
        logger.error(f"无效的 number 参数: {number}，支持的范围为 1-100 的整数")
        return None

    # 验证 city_type 参数
    valid_types = {"cn", "world", "overseas"}
    if city_type not in valid_types:
        logger.error(f"无效的 city_type 参数: {city_type}，支持的值: {', '.join(sorted(valid_types))}")
        return None

    url = f"https://{api_host}/geo/v2/city/top"
    params = {"number": str(number), "type": city_type, "lang": lang}

    try:
        response = httpx.get(url, headers=auth_header, params=params)

        if response.status_code != 200:
            logger.error(
                f"获取热门城市数据失败 - 状态码: {response.status_code}, 响应: {response.text}"
            )
            return None

        top_cities_data = response.json()
        logger.info(f"成功获取热门城市数据，类型: {city_type}，数量: {number}")
        return top_cities_data

    except httpx.RequestError as e:
        logger.error(f"请求热门城市数据时发生网络错误: {e}")
        return None
    except Exception as e:
        logger.error(f"获取热门城市数据时发生未知错误: {e}")
        return None


@mcp.tool()
def search_poi(
    location: str,
    keyword: str,
    poi_type: str,
    city: Optional[str] = None,
    radius: int = 5000,
    page: int = 1,
    lang: str = "zh"
) -> Optional[Dict[str, Any]]:
    """
    根据关键词搜索兴趣点(Point of Interest)

    支持全球POI搜索，包括地标、建筑物、景点等多种类型的兴趣点

    Args:
        location: 必选，搜索地区的经纬度坐标或LocationID，格式: "116.41,39.92" 或 "101010100"
                  也支持传入城市名（会尝试解析为经纬度）
        keyword: 必选，搜索关键词，如 "故宫"、"博物馆"、"景点" 等
        poi_type: 必选，POI类型，支持：
                  - "scenic": 景点
                  - "TSTA": 潮汐站点
        city: 可选，限定搜索城市，支持LocationID或城市名称
        radius: 可选，搜索半径，单位: 米，默认5000米，范围100-50000
        page: 可选，页码，默认1
        lang: 可选，多语言设置，默认中文 "zh"

    Returns:
        包含POI搜索结果的 JSON 数据，如果失败返回 None

    Examples:
        >>> search_poi("北京", "博物馆", "scenic", radius=10000)
        {
            "code": "200",
            "poi": [
                {
                    "id": "B000A81UYB",
                    "name": "故宫博物院",
                    "country": "CN",
                    "path": "北京市东城区景山前街4号",
                    "type": "风景名胜",
                    "typecode": "1001",
                    "address": "北京市东城区景山前街4号",
                    "location": "116.39,39.92",
                    "admindistrict": "东城区",
                    "city": "北京",
                    "province": "北京"
                },
                ...
            ]
        }
    """
    # 验证必需参数
    if not location or not str(location).strip():
        logger.error("location 参数不能为空")
        return None

    if not keyword or not str(keyword).strip():
        logger.error("keyword 参数不能为空")
        return None

    # 验证POI类型
    if poi_type not in POI_TYPES:
        logger.error(f"无效的POI类型: {poi_type}，支持的类型: {', '.join(POI_TYPES.keys())}")
        return None

    # 验证radius参数
    if not isinstance(radius, int) or radius < 100 or radius > 50000:
        logger.error(f"无效的 radius 参数: {radius}，支持的范围为 100-50000 米")
        return None

    # 验证page参数
    if not isinstance(page, int) or page < 1:
        logger.error(f"无效的 page 参数: {page}，必须为大于0的整数")
        return None

    # 处理location参数
    loc_value = str(location).strip()

    if "," in loc_value:
        # 经纬度坐标处理
        try:
            parts = [s.strip() for s in loc_value.split(",", 1)]
            if len(parts) != 2:
                logger.error(f"坐标格式错误: {loc_value}，期望格式: 经度,纬度")
                return None

            lon = float(parts[0])
            lat = float(parts[1])

            # 验证经纬度范围
            if not (-180 <= lon <= 180):
                logger.error(f"经度超出有效范围 [-180, 180]: {lon}")
                return None
            if not (-90 <= lat <= 90):
                logger.error(f"纬度超出有效范围 [-90, 90]: {lat}")
                return None

            # 格式化坐标
            formatted_loc = f"{lon:.2f},{lat:.2f}"
            logger.info(f"使用坐标搜索: {formatted_loc}")

        except ValueError:
            logger.error(f"无法解析坐标: {loc_value}")
            return None
    elif loc_value.isdigit():
        # LocationID处理
        formatted_loc = loc_value
        logger.info(f"使用LocationID搜索: {formatted_loc}")
    else:
        # 城市名称处理
        location_id = _get_city_location(loc_value)
        if not location_id:
            logger.error(f"无法获取城市 '{loc_value}' 的LocationID")
            return None
        formatted_loc = location_id
        logger.info(f"城市 '{loc_value}' 解析为LocationID: {formatted_loc}")

    url = f"https://{api_host}/geo/v2/poi/lookup"
    params = {
        "location": formatted_loc,
        "keyword": keyword.strip(),
        "type": poi_type,
        "radius": str(radius),
        "page": str(page),
        "lang": lang
    }

    # 如果指定了城市，添加city参数
    if city and city.strip():
        if "," in city.strip():
            # 如果city也是坐标，需要转换为LocationID
            city_loc = _get_city_location(city.strip())
            if city_loc:
                params["city"] = city_loc
        elif city.strip().isdigit():
            # 如果是LocationID
            params["city"] = city.strip()
        else:
            # 如果是城市名，获取LocationID
            city_location_id = _get_city_location(city.strip())
            if city_location_id:
                params["city"] = city_location_id

    try:
        response = httpx.get(url, headers=auth_header, params=params)

        if response.status_code != 200:
            logger.error(
                f"POI搜索失败 - 状态码: {response.status_code}, 响应: {response.text}"
            )
            return None

        poi_data = response.json()
        logger.info(f"成功搜索POI，关键词: '{keyword}'，类型: {poi_type}，位置: {loc_value}")
        return poi_data

    except httpx.RequestError as e:
        logger.error(f"POI搜索请求时发生网络错误: {e}")
        return None
    except Exception as e:
        logger.error(f"POI搜索时发生未知错误: {e}")
        return None


@mcp.tool()
def search_poi_range(
    location: str,
    poi_type: str,
    radius: int = 5,
    city: Optional[str] = None,
    page: int = 1,
    lang: str = "zh"
) -> Optional[Dict[str, Any]]:
    """
    在指定坐标点周围的圆形区域内搜索POI

    支持按距离排序的POI范围搜索，适合查找附近的兴趣点

    Args:
        location: 必选，中心点的经纬度坐标，格式: "116.41,39.92"（经度,纬度）
                  注意：此API强制要求使用经纬度坐标，不支持城市名称
        poi_type: 必选，POI类型，支持：
                  - "scenic": 景点
                  - "TSTA": 潮汐站点
        radius: 可选，搜索半径，单位：公里，范围1-50，默认5公里
        city: 可选，限定搜索城市，支持LocationID或城市名称
        page: 可选，页码，默认1
        lang: 可选，多语言设置，默认中文 "zh"

    Returns:
        包含POI范围搜索结果的 JSON 数据，包含距离信息，如果失败返回 None

    Examples:
        >>> search_poi_range("116.41,39.92", "scenic", 2)
        {
            "code": "200",
            "poi": [
                {
                    "id": "B000A81UYB",
                    "name": "全聚德烤鸭店",
                    "country": "CN",
                    "path": "北京市东城区前门大街30号",
                    "type": "餐饮服务",
                    "typecode": "0501",
                    "address": "北京市东城区前门大街30号",
                    "location": "116.39,39.92",
                    "distance": "1200",
                    "admindistrict": "东城区",
                    "city": "北京",
                    "province": "北京"
                },
                ...
            ]
        }
    """
    # 验证必需参数
    if not location or not str(location).strip():
        logger.error("location 参数不能为空，需为经度,纬度坐标（如 116.41,39.92）")
        return None

    if not isinstance(page, int) or page < 1:
        logger.error(f"无效的 page 参数: {page}，必须为大于0的整数")
        return None

    # 验证radius参数（范围1-50公里）
    if not isinstance(radius, int) or radius < 1 or radius > 50:
        logger.error(f"无效的 radius 参数: {radius}，支持的范围为 1-50 公里")
        return None

    # 使用整数radius值
    radius_int = radius

    # 验证POI类型
    if poi_type not in POI_TYPES:
        logger.error(f"无效的POI类型: {poi_type}，支持的类型: {', '.join(POI_TYPES.keys())}")
        return None

    loc_value = str(location).strip()

    # 强制要求坐标格式
    if "," not in loc_value:
        logger.error(
            f"location 参数格式错误：'{loc_value}'，POI范围搜索仅支持经纬度坐标，期望格式：经度,纬度（如 116.41,39.92）"
        )
        return None

    try:
        # 解析并验证经纬度坐标
        parts = [s.strip() for s in loc_value.split(",", 1)]
        if len(parts) != 2:
            logger.error(f"坐标格式错误: {loc_value}，期望格式: 经度,纬度")
            return None

        lon = float(parts[0])
        lat = float(parts[1])

        # 验证经纬度范围
        if not (-180 <= lon <= 180):
            logger.error(f"经度超出有效范围 [-180, 180]: {lon}")
            return None
        if not (-90 <= lat <= 90):
            logger.error(f"纬度超出有效范围 [-90, 90]: {lat}")
            return None

        # 格式化坐标为两位小数
        formatted_loc = f"{lon:.2f},{lat:.2f}"
        logger.info(f"使用坐标范围搜索：{loc_value} → {formatted_loc}")

    except ValueError as e:
        logger.error(f"无法解析坐标参数：{loc_value}，错误：{e}")
        return None

    url = f"https://{api_host}/geo/v2/poi/range"
    params = {
        "location": formatted_loc,
        "type": poi_type,
        "radius": str(radius_int),  # 转换为整数
        "page": str(page),
        "lang": lang
    }

    # 如果指定了城市，添加city参数
    if city and city.strip():
        if city.strip().isdigit():
            # 如果是LocationID
            params["city"] = city.strip()
        else:
            # 如果是城市名，获取LocationID
            city_location_id = _get_city_location(city.strip())
            if city_location_id:
                params["city"] = city_location_id

    try:
        response = httpx.get(url, headers=auth_header, params=params)

        if response.status_code != 200:
            logger.error(
                f"POI范围搜索失败 - 状态码: {response.status_code}, 响应: {response.text}"
            )
            return None

        poi_range_data = response.json()
        logger.info(f"成功搜索POI范围，中心点: {formatted_loc}，类型: {poi_type}，半径: {radius_int}公里")
        return poi_range_data

    except httpx.RequestError as e:
        logger.error(f"POI范围搜索请求时发生网络错误: {e}")
        return None
    except Exception as e:
        logger.error(f"POI范围搜索时发生未知错误: {e}")
        return None


@app.command()
def http() -> None:
    """
    命令行入口函数

    用于支持通过 pip 安装后的命令行调用
    """
    try:
        logger.info("正在启动和风天气MCP服务...")
        logger.info(f"API主机: {api_host}")
        if api_key:
            logger.info(f"API KEY: {api_key[:10]}...")
        else:
            logger.info(f"项目ID: {project_id}")
            logger.info(f"密钥ID: {key_id}")
        logger.info("服务启动成功，等待连接...")
        mcp.run(transport="streamable-http")
    except KeyboardInterrupt:
        logger.info("服务被用户中断")
    except Exception as e:
        logger.error(f"服务启动失败: {e}")
        raise


@app.command()
def stdio() -> None:
    """
    命令行入口函数

    用于支持通过 pip 安装后的命令行调用
    """
    try:
        logger.info("正在启动和风天气MCP服务...")
        logger.info(f"API主机: {api_host}")
        if api_key:
            logger.info(f"API KEY: {api_key[:10]}...")
        else:
            logger.info(f"项目ID: {project_id}")
            logger.info(f"密钥ID: {key_id}")
        logger.info("服务启动成功，等待连接...")
        mcp.run(transport="stdio")
    except KeyboardInterrupt:
        logger.info("服务被用户中断")
    except Exception as e:
        logger.error(f"服务启动失败: {e}")
        raise


def main() -> None:
    """
    主函数入口

    解析命令行参数并启动相应的MCP服务
    """
    app()


if __name__ == "__main__":
    """
    主程序入口点

    启动和风天气MCP服务，使用streamable-http传输协议
    确保在运行前已正确配置所有必需的环境变量
    """
    main()
