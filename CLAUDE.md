# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个基于 Model Context Protocol (MCP) 的和风天气服务，提供天气预报、气象预警、空气质量、历史数据、天文信息等多种气象数据查询功能。项目使用 Python 开发，支持 stdio 和 streamable-http 两种 MCP 传输协议，支持 API KEY 和 JWT 数字签名两种认证方式。

## 常用开发命令

### 环境设置
```bash
# 安装依赖（推荐使用 uv）
uv sync

# 或使用 pip
pip install -e .

# 复制环境变量配置模板
cp .env.example .env
# 然后编辑 .env 文件填入真实的和风天气 API 配置
```

### 代码质量检查
```bash
# 代码格式化和检查
ruff check src/
ruff format src/

# 类型检查
mypy src/
```

### 运行服务
```bash
# stdio 模式（推荐用于本地开发）
hefeng-weather-mcp stdio

# http 模式（推荐用于远程访问）
hefeng-weather-mcp http

# 或使用 uv 直接运行
uv run hefeng-weather-mcp stdio
uv run hefeng-weather-mcp http
```

### 服务管理
```bash
# 查看运行状态
ps aux | grep hefeng-weather-mcp

# 停止所有服务
pkill -f hefeng-weather-mcp

# 分别停止不同模式
pkill -f "hefeng-weather-mcp stdio"
pkill -f "hefeng-weather-mcp http"
```

### 生成密钥对（仅首次配置需要）
```bash
openssl genpkey -algorithm ED25519 -out ed25519-private.pem \
&& openssl pkey -pubout -in ed25519-private.pem > ed25519-public.pem
```

## 核心架构

### 主要组件结构

1. **主模块** (`src/hefeng_weather_mcp/main.py`):
   - 包含所有 MCP 工具函数
   - JWT 认证逻辑
   - 和风天气 API 交互
   - 命令行入口处理

2. **认证系统**:
   - **优先使用 API KEY 认证**：简单快捷，配置方便
   - **JWT 数字签名认证**：备用方案，使用 EdDSA 算法
   - 私钥支持文件路径或直接内容加载
   - JWT 令牌 15 分钟自动过期（仅JWT模式）

3. **位置解析**:
   - `_get_city_location()` 函数负责将城市名转换为 LocationID 或经纬度
   - 支持中文城市名自动解析
   - 可选择返回 LocationID 或经纬度格式

### MCP 工具分类

1. **基础天气工具**:
   - `get_weather_now()`: 实时天气（温度、体感温度、湿度、气压等）
   - `get_weather()`: 3-30天天气预报（支持3d/7d/10d/15d/30d）
   - `get_hourly_weather()`: 24/72/168小时逐小时预报
   - `get_weather_history()`: 历史天气（最多10天）

2. **空气质量工具**:
   - `get_air_quality()`: 实时空气质量（AQI、污染物浓度）
   - `get_air_quality_history()`: 历史空气质量数据

3. **生活指数工具**:
   - `get_indices()`: 16种生活指数预报（运动、洗车、穿衣、感冒等）

4. **预警信息工具**:
   - `get_warning()`: 气象灾害预警

5. **天文数据工具**:
   - `get_astronomy_sun()`: 日出日落时间（全球任意地点，未来60天内）
   - `get_astronomy_moon()`: 月升月落时间和24小时逐小时月相数据（含照明度）

6. **分钟级预报工具**:
   - `get_minutely_5m()`: 未来2小时5分钟级降水预报

### 工具详细说明

#### 天文数据工具详细参数

**`get_astronomy_sun(location, date, lang)`**
- `location`: 位置信息（支持城市名、LocationID、经纬度）
- `date`: 日期（yyyyMMdd格式，支持今天到未来60天）
- `lang`: 语言（默认"zh"中文）
- 返回：日出日落时间，支持全球任意地点

**`get_astronomy_moon(location, date, lang)`**
- `location`: 位置信息（支持城市名、LocationID、经纬度）
- `date`: 日期（yyyyMMdd格式，支持今天到未来60天）
- `lang`: 语言（默认"zh"中文）
- 返回：月升月落时间 + 24小时逐小时月相数据（含月相名称、照明度百分比）

#### 天文数据使用示例

```python
# 日出日落查询
get_astronomy_sun("北京", "20251029")           # 城市名
get_astronomy_sun("101010100", "20251029")      # LocationID
get_astronomy_sun("116.41,39.92", "20251029")   # 经纬度

# 月相查询
get_astronomy_moon("上海", "20251101")           # 返回24小时月相数据
get_astronomy_moon("121.47,31.23", "20251101")  # 支持全球坐标
```

### 关键设计模式

1. **统一错误处理**: 所有工具函数都使用相同的异常处理模式，返回 None 表示失败
2. **位置参数灵活性**: 支持城市名、LocationID、经纬度三种位置输入方式
3. **日志记录**: 使用标准的 logging 模块记录操作日志
4. **环境变量配置**: 所有敏感配置通过环境变量管理

## 环境配置

### 认证方式

#### API KEY 认证（推荐）
```env
HEFENG_API_HOST=你的API主机地址
HEFENG_API_KEY=你的API KEY
```

#### JWT 数字签名认证（备用）
```env
HEFENG_API_HOST=你的API主机地址
HEFENG_PROJECT_ID=你的项目ID
HEFENG_KEY_ID=你的凭据ID
HEFENG_PRIVATE_KEY_PATH=./ed25519-private.pem
```

### API 主机地址
- **商业版API**: 通常为自定义域名（如 `your-domain.qweatherapi.com`）
- **开发环境**: `devapi.qweather.com`
- **生产环境**: `api.qweather.com`

## 环境依赖

### 系统要求
- Python >= 3.11
- OpenSSL（用于密钥生成，仅JWT认证需要）
- 和风天气开发者账号

### 关键依赖包
- `mcp[cli]>=1.12.0`: MCP 框架
- `httpx>=0.28.1`: HTTP 客户端
- `cryptography>=45.0.5`: 加密支持（JWT认证）
- `pyjwt>=2.10.1`: JWT 令牌生成（JWT认证）
- `python-dotenv>=1.1.1`: 环境变量加载
- `typer>=0.16.0`: 命令行界面

## 代码规范

- 使用 `ruff` 进行代码格式化和静态检查
- 使用 `mypy` 进行类型检查
- 所有函数都有详细的 docstring 文档
- 遵循 PEP 8 编码规范
- 使用类型提示提高代码可读性