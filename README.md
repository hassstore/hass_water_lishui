# Lishui Water Fee for Home Assistant（丽水供排水水费）

> **免责声明**
>
> 本项目为非官方 Home Assistant 集成，未获得丽水市供排水有限责任公司或相关平台
> 的授权、认可或支持。项目仅用于学习、交流与技术研究，请勿用于商业用途或其他
> 违反适用法律、平台规则和服务条款的行为。

把微信小程序「丽水供排水」的水费账单接入 Home Assistant，生成最新水费金额、
用水量、抄表读数、缴费状态等传感器。数据接口与小程序一致，数值与小程序
「水费账单」页面相同。

支持多水表，每个水表号一条独立集成条目；账单按月出账，默认每 6 小时轮询一次。

---

## 要求

- Home Assistant **2025.8** 或更新版本（集成使用 `OptionsFlowWithReload`，
  该 API 自 2025.8 起提供）
- 丽水供排水的水表号（户号，见账单或微信小程序）
- 无 PyPI 依赖，仅使用 HA 内置的 aiohttp 会话

## 安装

**HACS（推荐）**

1. HACS → ⋮ → **Custom repositories**
2. 类型选 `Integration`，仓库填 `https://github.com/hassstore/hass_water_lishui`
3. 搜索 **Lishui Water Fee** → **Download**
4. 重启 Home Assistant（系统重启，不是"重新加载配置"）

**手动**

从 [Releases](https://github.com/hassstore/hass_water_lishui/releases) 下载
`hass_water_lishui.zip`，解压到配置目录，使路径为
`custom_components/hass_water_lishui/`，重启 Home Assistant。

## 配置

**设置 → 设备与服务 → 添加集成 → Lishui Water Fee**：

| 字段 | 说明 |
| --- | --- |
| 水表号 | 户号/表号，见纸质账单或微信小程序「丽水供排水」户号绑定页 |
| 计费年度 | 要查询的年度，例如 `2026`；接口按年度返回账单列表 |
| 用户 Token | 可留空。部分账户字段（如余额）需要小程序登录态时才填写 |

**Token 获取（可选）**：当接口开始要求登录态时——

1. 微信打开小程序「丽水供排水」并登录绑定户号；
2. 抓包或调试小程序网络请求，找到发往 `wx.lswater.cn` 的请求；
3. 复制请求头中的 `Token` 值粘贴进配置框。

Token 过期后集成会弹出「需要重新认证」卡片，点击后粘贴新 Token 即可
（reauth 流程），无需删除重建集成。

## 传感器

每个水表生成一个设备（名称为条目名，如「丽水水费 &lt;水表号&gt;」），包含以下传感器：

| 传感器 | 单位 | 说明 |
| --- | --- | --- |
| 最新水费金额 | CNY | 最新一期账单金额（接口 `fareValue`），属性里附带最近 12 期历史账单（`history_bills`，实时可读但不写入 recorder） |
| 最新用水量 | m³ | 本期用水量，由 `currDegree - lastDegree` 计算 |
| 账户余额 | CNY | 账户余额（接口 `balance`，**默认禁用**，设备页可手动开启） |
| 账单缴费状态 | — | `已缴费` / `未缴费`（接口 `billFlag == 0` 为已缴） |
| 最新抄表读数 | m³ | 本期抄表读数（接口 `currDegree`，**默认禁用**） |
| 上期抄表读数 | m³ | 上期抄表读数（接口 `lastDegree`，**默认禁用**） |

通用属性：`fare_month`（账期）、`curr_copy_date` / `last_copy_date`（抄表日期）、
`is_paid`（是否已缴）。

状态语义：

- `unknown`：接口通了但该字段无值（例如还没出账），`native_value` 返回 `None`。
- 用水量算出来为负（换表/清零）时返回 `unknown`，不污染长期统计。
- `unavailable`：整轮轮询失败（接口不可达），下一轮自动恢复。
- 缴费状态只在接口返回 `billFlag` 字段时才更新，不会用 0 冒充真实值。

## 修改计费年度

接口按**年度**返回账单，所以计费年度属于「连接设置」而非偏好：跨年后用
**设置 → 集成 → Lishui Water Fee → ⋮ → 重新配置**，只改年度，条目、设备与
实体（连同历史数据）都会保留。若新年度还没出账，会提示 `no_data`，过几天再试即可。

## 选项

**设置 → 集成 → Lishui Water Fee → 配置**：

| 字段 | 默认 | 说明 |
| --- | --- | --- |
| 轮询间隔 | 6 小时 | 账单按月出账，1–48 小时可调；更频繁没有意义 |

修改后自动重载该条目生效。

## 工作原理（简述）

- 接口：`GET http://wx.lswater.cn/upfscapi/wxClient/getFareList`，
  参数 `cardNo` / `clientNo`（同水表号）、`year`；请求头带小程序的
  `Appid` 与可选 `Token`
- 返回按 `fareMonth` 倒序取最新一期，其余进入 `history_bills` 属性
- 字段对应：`fareValue` → 水费金额，`balance` → 账户余额，
  `currDegree`/`lastDegree` → 本/上期读数（用水量取差值），
  `billFlag == 0` → 已缴费
- Token 类错误（401/403 或报文含 token）会触发 HA 重新认证卡片，其余错误
  按暂时性失败处理，保留旧数据

## 常见问题

| 问题 | 处理 |
| --- | --- |
| `cannot_connect` | 检查 HA 能否访问 `wx.lswater.cn`（HTTP 80）；部分地区运营商拦截，需换 DNS 或代理 |
| `invalid_auth` / 弹出重新认证 | Token 过期，粘贴新 Token；留空 Token 仍报错说明接口改为必须登录态 |
| `no_data` | 该水表号 + 计费年度没有账单：核对水表号，或改选更早的年度 |
| 金额字段为空 | 该接口对未登录请求不返回余额类字段，填入 Token 后重试 |
| `already_configured` | 同一水表号已添加过；要换 Token 走「配置」或等待重认证提示 |
| 需要把数据发给维护者 | 设备页 → ⋯ → **下载诊断信息**：Token 已脱敏，只含轮询状态与账单统计 |

## 安全须知

- **非官方接口**，无文档背书，响应字段可能随小程序版本变化
- Token 等同于小程序登录态，存放在 `.storage/core.config_entries`，
  请像保护密码一样保护其备份
- 日志中不会打印 Token 与完整响应体

## 开发与发布

- 测试：`pip install pytest-homeassistant-custom-component && pytest`
  （覆盖 config flow / reauth / reconfigure / options / 空数据语义 / 诊断脱敏）
- `client.py` 只依赖 aiohttp 且**不 import homeassistant**，可按文件头示例用
  importlib 单独加载调试
- 推送 `vX.Y.Z` tag（与 `manifest.json` 版本一致）由
  [release.yml](https://github.com/hassstore/hass_water_lishui/blob/main/.github/workflows/release.yml)
  自动打包 `hass_water_lishui.zip` 并创建 Release
- 品牌图标用 `python3 tools/make_icon.py` 重新生成

## 许可证

MIT，见 [LICENSE](https://github.com/hassstore/hass_water_lishui/blob/main/LICENSE)。
由 [@hassstore](https://github.com/hassstore) 维护。
