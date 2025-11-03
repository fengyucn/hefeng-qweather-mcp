# 和风天气 MCP 服务

一个基于 Model Context Protocol (MCP) 的和风天气服务，提供天气预报、气象预警、空气质量、历史数据、天文信息等多种气象数据查询功能。

## 功能特性

- **天气预报**: 获取3-30天详细天气预报（支持3d/7d/10d/15d/30d）
- **格点天气**: 全球任意坐标高分辨率数值预报天气（3-5公里分辨率）
- **气象预警**: 查询实时气象灾害预警信息
- **生活指数**: 获取各类生活指数预报，如洗车、穿衣、感冒等（16种指数）
- **空气质量**: 获取城市的空气质量指数（AQI）及主要污染物信息
- **逐小时预报**: 获取未来 24/72/168 小时逐小时天气（温度、天气状况、风力/风速/风向、相对湿度、气压、降水概率、露点、云量等）
- **实况天气**: 获取近实时天气（温度、体感温度、风、湿度、气压、降水量、能见度、露点、云量等）
- **历史数据**: 获取历史天气和空气质量数据（最多10天）
- **天文数据**: 获取日出日落时间、月相月升月落信息
- **分钟级预报**: 获取未来2小时5分钟级降水预报
- **双认证支持**: 支持 API KEY 和 JWT + EdDSA 数字签名认证
- **详细日志**: 完整的操作日志和错误处理

## 安装

```bash
uv tool install hefeng-qweather-mcp
```

或使用 pip 安装：

```bash
pip install hefeng-qweather-mcp
```

```env
# 推荐配置 - API KEY 认证（简单快捷）
HEFENG_API_HOST=你的API主机地址
HEFENG_API_KEY=你的API KEY

# 备用配置 - JWT 数字签名认证
# HEFENG_PROJECT_ID=你的项目ID
# HEFENG_KEY_ID=你的凭据ID
# HEFENG_PRIVATE_KEY_PATH=./ed25519-private.pem

# 可选：直接加载密钥内容，方便远程部署
# HEFENG_PRIVATE_KEY=
```

## 使用

### 快速开始

1. **配置环境变量**
   ```bash
   # 复制并编辑配置文件
   cp .env.example .env

   # 填入您的和风天气 API 配置
   # 推荐使用 API KEY 认证方式
   ```

2. **启动服务器**
   ```bash
   # STDIO 模式（推荐用于本地开发）
   hefeng-qweather-mcp stdio

   # HTTP 模式（推荐用于远程访问）
   hefeng-qweather-mcp http
   ```

### 运行模式

#### HTTP 模式

HTTP 模式提供 Web API 接口，适合远程访问和 Web 集成：

```bash
hefeng-qweather-mcp http
```

服务器启动后将在 `http://127.0.0.1:8000` 运行，MCP 端点为 `http://127.0.0.1:8000/mcp`。

**VS Code 配置：**
```json
{
  "servers": {
    "hefeng-qweather-mcp": {
      "url": "http://127.0.0.1:8000/mcp",
      "type": "http"
    }
  },
  "inputs": []
}
```

#### STDIO 模式

STDIO 模式通过标准输入输出通信，适合本地开发：

```bash
hefeng-qweather-mcp stdio
```

**VS Code 配置：**
```json
{
  "servers": {
    "hefeng-qweather-mcp": {
      "type": "stdio",
      "command": "hefeng-qweather-mcp stdio"
    }
  },
  "inputs": []
}
```

**使用 uv 运行：**
```json
{
  "servers": {
    "hefeng-qweather-mcp": {
      "type": "stdio",
      "command": "uvx hefeng-qweather-mcp stdio",
      "envFile": "${workspaceFolder}/.env"
    }
  },
  "inputs": []
}
```

### 管理服务器

#### 查看运行状态
```bash
# 查看后台进程
ps aux | grep hefeng-qweather-mcp
```

#### 停止服务器
```bash
# 停止所有模式
pkill -f hefeng-qweather-mcp

# 或分别停止
pkill -f "hefeng-qweather-mcp stdio"
pkill -f "hefeng-qweather-mcp http"
```

#### 验证配置

服务启动后，可以通过以下方式验证配置是否正确：

1. **检查日志输出** - 确认 API 主机和认证信息正确显示
2. **在 VS Code 中测试** - 使用 MCP 工具查询天气数据
3. **检查服务状态** - 确保服务正常运行无错误

如果遇到配置问题，请检查：

- 环境变量是否正确设置
- API KEY 是否有效且未过期
- 网络连接是否正常

### 使用示例

#### 天文数据查询示例

```python
# 查询北京今天的日出日落时间
get_astronomy_sun("北京", "20251029")
# 结果：日出 06:40, 日落 17:17

# 查询上海的月相信息
get_astronomy_moon("上海", "20251101")
# 结果：月升 13:24, 月落 23:09, 月相：上弦月

# 使用经纬度查询（全球任意地点）
get_astronomy_sun("116.41,39.92", "20251029")  # 北京坐标
get_astronomy_moon("121.47,31.23", "20251101")  # 上海坐标

# 查询未来日期的天文数据
get_astronomy_sun("广州", "20251225")  # 圣诞节
get_astronomy_moon("深圳", "20260101")  # 元旦
```

#### 多天天气预报示例

```python
# 查询不同天数的天气预报
get_weather("北京", "3d")   # 3天预报（默认）
get_weather("上海", "7d")   # 7天预报
get_weather("广州", "15d")  # 15天预报
get_weather("深圳", "30d")  # 30天预报
```

### 可用的 MCP 工具

您的 MCP 服务器提供以下天气查询工具：

#### 基础天气工具
- **`get_weather_now`** - 获取实时天气数据
  - 参数：`city`（城市名）或 `location`（位置ID/坐标）
  - 返回：温度、体感温度、天气状况、湿度、气压等

- **`get_weather`** - 获取天气预报
  - 参数：`city`（城市名）、`days`（预报天数：3d/7d/10d/15d/30d，默认3d）
  - 返回：指定天数的每日天气详情

- **`get_hourly_weather`** - 获取逐小时天气预报
  - 参数：`hours`（24h/72h/168h）、`city` 或 `location`
  - 返回：逐小时温度、天气、风力、湿度等

#### 空气质量工具
- **`get_air_quality`** - 获取实时空气质量
  - 参数：`city`（城市名）
  - 返回：AQI、污染物浓度、健康建议

- **`get_air_quality_history`** - 获取历史空气质量
  - 参数：`city`（城市名）、`days`（1-10天）
  - 返回：历史空气质量数据

#### 生活指数工具
- **`get_indices`** - 获取生活指数预报
  - 参数：`city`（城市名）、`days`（1d/3d）、`index_types`（指数类型）
  - 返回：16种生活指数（运动、洗车、穿衣、感冒等）

#### 预警和天文工具
- **`get_warning`** - 获取气象预警信息
  - 参数：`city`（城市名）
  - 返回：实时气象灾害预警

- **`get_astronomy_sun`** - 获取日出日落时间
  - 参数：`location`（城市名/LocationID/坐标）、`date`（yyyyMMdd格式，支持未来60天）
  - 返回：日出日落时间（支持全球任意地点）

- **`get_astronomy_moon`** - 获取月相和月升月落信息
  - 参数：`location`（城市名/LocationID/坐标）、`date`（yyyyMMdd格式，支持未来60天）
  - 返回：月升月落时间、24小时逐小时月相数据（含月相名称、照明度）

#### 历史和详细数据工具
- **`get_weather_history`** - 获取历史天气数据
  - 参数：`city` 或 `location`、`days`（1-10天）
  - 返回：历史天气数据

- **`get_minutely_5m`** - 获取分钟级降水预报
  - 参数：`location`（坐标或城市名）
  - 返回：未来2小时5分钟级降水数据

#### 格点天气工具（新功能）
- **`get_grid_weather_now`** - 获取格点实时天气数据
  - 参数：`location`（经纬度坐标）、`lang`（语言，默认zh）、`unit`（单位，默认m）
  - 返回：高分辨率（3-5公里）实时天气数据，支持全球任意坐标

- **`get_grid_weather_daily`** - 获取格点每日天气预报
  - 参数：`location`（经纬度坐标）、`lang`（语言，默认zh）、`unit`（单位，默认m）
  - 返回：格点数值模式的每日天气预报

- **`get_grid_weather_hourly`** - 获取格点逐小时天气预报
  - 参数：`location`（经纬度坐标）、`lang`（语言，默认zh）、`unit`（单位，默认m）
  - 返回：格点数值模式的逐小时天气预报

## 前置要求

- Python >= 3.11
- OpenSSL (用于生成密钥对)
- 和风天气开发者账号

## 开发

### 1. 克隆项目

```bash
git clone https://github.com/fengyucn/hefeng-qweather-mcp.git
cd hefeng-qweather-mcp
```

### 2. 安装依赖

使用 pip:

```bash
pip install -e .
```

或使用 uv (推荐):

```bash
uv sync
```

### 3. 获取和风天气 API 配置

#### 方式一：API KEY 认证（推荐）

1. 访问 [和风天气控制台](https://console.qweather.com/project/)
2. 注册/登录账号
3. 创建项目并获取 **API KEY**
4. 复制配置模板文件：

```bash
cp .env.example .env
```

1. 编辑 `.env` 文件：

```env
# API KEY 认证配置
HEFENG_API_HOST=你的API主机地址
HEFENG_API_KEY=你的API KEY
```

#### 方式二：JWT 数字签名认证（备用）

如果需要使用 JWT 认证：

1. 在和风天气控制台创建项目并记录 **Project ID**
2. 生成 EdDSA 密钥对：

```bash
openssl genpkey -algorithm ED25519 -out ed25519-private.pem \
&& openssl pkey -pubout -in ed25519-private.pem > ed25519-public.pem
```

3. 在控制台中创建数字签名凭据，上传公钥文件
4. 配置 `.env` 文件：

```env
# JWT 认证配置
HEFENG_API_HOST=你的API主机地址
HEFENG_PROJECT_ID=你的项目ID
HEFENG_KEY_ID=你的凭据ID
HEFENG_PRIVATE_KEY_PATH=./ed25519-private.pem
```

**注意：** 推荐优先使用 API KEY 认证，配置更简单。JWT 认证适合需要更高安全性的场景。

### 开发指南

1. **代码风格**: 项目使用 `ruff` 进行代码格式化和检查
2. **类型检查**: 使用 `mypy` 进行静态类型检查
3. **测试**: 建议为新功能添加相应的单元测试
4. **文档**: 确保所有新功能都有详细的 docstring 文档

## 版本历史

### v0.4.0 (最新)

- ✅ 新增格点天气接口：高分辨率数值预报天气查询
- ✅ 支持全球任意坐标的实时天气查询（3-5公里分辨率）
- ✅ 新增格点每日天气预报和逐小时天气预报
- ✅ 基于数值预报模型，提供精确坐标天气数据
- ✅ 完善多语言支持和单位选择功能

### v0.3.0

- ✅ 新增天文数据接口：日出日落时间和月相月升月落
- ✅ 新增分钟级降水预报接口（未来2小时5分钟级）
- ✅ 支持多种天气预报时长：3d/7d/10d/15d/30d
- ✅ 支持24/72/168小时逐小时天气预报
- ✅ 完善历史数据查询（天气和空气质量，最多10天）
- ✅ 优化认证系统，优先使用API KEY认证
- ✅ 完善错误处理和日志记录

### v0.2.1

- 基础天气查询功能
- JWT数字签名认证支持
- 空气质量查询
- 生活指数查询

## 许可证

MIT License

## 贡献指南

我们欢迎任何形式的贡献！

### 提交 Issue

如果你发现了 bug 或有功能建议，请：

1. 查看现有的 Issue，避免重复提交
2. 使用清晰的标题和详细的描述
3. 如果是 bug 报告，请包含重现步骤和环境信息

## 相关链接

- [和风天气官网](https://www.qweather.com/)
- [和风天气开发者控制台](https://console.qweather.com/project/)
- [和风天气 API 文档](https://dev.qweather.com/docs/api/)
- [Model Context Protocol](https://modelcontextprotocol.io/)

## 联系方式

如有问题或建议，请通过以下方式联系：


- 🐛 Issues: [GitHub Issues](https://github.com/fengyucn/hefeng-qweather-mcp/issues)
- 💬 讨论: [GitHub Discussions](https://github.com/fengyucn/hefeng-qweather-mcp/discussions)

---

**免责声明**: 本项目仅供学习和研究使用，请遵守和风天气的服务条款和 API 使用规范。
