"""
和风天气 MCP 服务

这是一个基于 Model Context Protocol (MCP) 的和风天气服务，提供天气预报、气象预警、
太阳辐射等多种气象数据查询功能。

功能特性:
- 获取未来三天天气预报
- 查询当前气象预警信息
- 获取太阳辐射逐小时预报

环境变量配置:
- HEFENG_API_HOST: 和风天气API主机地址
- HEFENG_PROJECT_ID: 项目ID
- HEFENG_KEY_ID: 密钥ID
- HEFENG_PRIVATE_KEY_PATH: 私钥文件路径

Author: yeisme
Version: 0.1.3
License: MIT
"""

import httpx
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv
import logging
import os
import time
import jwt
from typing import Optional, Dict, Any
import typer

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("hefeng_weather_mcp")

# 加载环境变量
load_dotenv()

# 初始化MCP服务
mcp = FastMCP("hefeng_weather_mcp")
app = typer.Typer()


# API配置常量
JWT_EXPIRY_SECONDS = 900  # JWT令牌过期时间（15分钟）
DEFAULT_FORECAST_DAYS = 3  # 默认天气预报天数
DEFAULT_SOLAR_HOURS = 24  # 默认太阳辐射预报小时数

# 从环境变量获取API配置
api_host = os.environ.get("HEFENG_API_HOST")
project_id = os.environ.get("HEFENG_PROJECT_ID")
key_id = os.environ.get("HEFENG_KEY_ID")
private_key_path = os.environ.get("HEFENG_PRIVATE_KEY_PATH")

# 验证必需的环境变量
if not all([api_host, project_id, key_id, private_key_path]):
    raise ValueError(
        "缺少必需的环境变量: HEFENG_API_HOST, HEFENG_PROJECT_ID, HEFENG_KEY_ID, HEFENG_PRIVATE_KEY_PATH"
    )

# 读取私钥文件
try:
    with open(private_key_path, "rb") as f:  # type: ignore
        private_key = f.read()
except FileNotFoundError:
    raise FileNotFoundError(f"私钥文件未找到: {private_key_path}")
except Exception as e:
    raise Exception(f"读取私钥文件失败: {e}")

# 生成JWT令牌
payload = {
    "iat": int(time.time()),
    "exp": int(time.time()) + JWT_EXPIRY_SECONDS,
    "sub": project_id,
}
headers = {"kid": key_id}

try:
    encoded_jwt = jwt.encode(payload, private_key, algorithm="EdDSA", headers=headers)
except Exception as e:
    raise Exception(f"JWT令牌生成失败: {e}")

# 认证头
auth_header = {
    "Authorization": f"Bearer {encoded_jwt}",
}


def _get_city_location(city: str) -> Optional[str]:
    """
    根据城市名称获取LocationID。

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
def get_weather(city: str) -> Optional[Dict[str, Any]]:
    """
    获取指定城市未来三天的天气预报。

    提供详细的天气信息，包括温度、湿度、风力、降水等数据。

    Args:
        city: 城市名称，支持中英文，如 '北京'、'上海'、'Beijing' 等

    Returns:
        包含未来三天天气预报的JSON数据，如果查询失败则返回None

    Examples:
        >>> get_weather("北京")
        {
            "code": "200",
            "updateTime": "2023-07-20T14:30+08:00",
            "daily": [
                {
                    "fxDate": "2023-07-20",
                    "tempMax": "32",
                    "tempMin": "24",
                    "textDay": "晴",
                    ...
                }
            ]
        }
    """
    if not city or not city.strip():
        logger.error("城市名称不能为空")
        return None

    city = city.strip()

    # 获取城市LocationID
    location_id = _get_city_location(city)
    if not location_id:
        logger.error(f"无法获取城市 '{city}' 的位置信息")
        return None

    url = (
        f"https://{api_host}/v7/weather/{DEFAULT_FORECAST_DAYS}d?location={location_id}"
    )

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
    获取指定城市的当前气象预警信息。

    提供官方发布的各类气象灾害预警，包括台风、暴雨、高温、寒潮等预警信息。

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


@app.command()
def http() -> None:
    """
    命令行入口函数。

    用于支持通过 pip 安装后的命令行调用。
    """
    try:
        logger.info("正在启动和风天气MCP服务...")
        logger.info(f"API主机: {api_host}")
        logger.info(f"项目ID: {project_id}")
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
    命令行入口函数。

    用于支持通过 pip 安装后的命令行调用。
    """
    try:
        logger.info("正在启动和风天气MCP服务...")
        logger.info(f"API主机: {api_host}")
        logger.info(f"项目ID: {project_id}")
        logger.info("服务启动成功，等待连接...")
        mcp.run(transport="stdio")
    except KeyboardInterrupt:
        logger.info("服务被用户中断")
    except Exception as e:
        logger.error(f"服务启动失败: {e}")
        raise


def main() -> None:
    """
    主函数入口。

    解析命令行参数并启动相应的MCP服务。
    """
    app()

if __name__ == "__main__":
    """
    主程序入口点。
    
    启动和风天气MCP服务，使用streamable-http传输协议。
    确保在运行前已正确配置所有必需的环境变量。
    """
    main()
