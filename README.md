# AI+智慧养殖数据大屏

基于 GitHub Actions + GitHub Pages 的自动化数据大屏，每15分钟从飞书 Base 拉取最新养殖数据并渲染为静态 HTML 页面。

## 功能特性

- **自动数据同步**：每15分钟通过 GitHub Actions 从飞书 Base 拉取数据
- **六大数据模块**：环境趋势、养殖事件、动物健康、饲料消耗、行业行情、告警统计
- **零服务器成本**：纯静态页面，通过 GitHub Pages 免费托管
- **响应式设计**：支持 PC 和移动端访问
- **数据安全**：API 凭证通过 GitHub Secrets 管理，不暴露于代码中

## 项目结构

```
smart-farming-dashboard/
├── .github/workflows/update-dashboard.yml   # GitHub Actions 工作流
├── scripts/
│   ├── fetch_data.py                        # 飞书 Base 数据拉取脚本
│   └── render_template.py                   # Jinja2 模板渲染脚本
├── template/
│   └── dashboard.html.j2                    # 数据大屏页面模板
├── config/
│   └── base_mapping.json                    # Base 表结构映射配置
├── requirements.txt                         # Python 依赖
└── README.md                                # 本文件
```

## 快速开始

### 步骤1：创建 GitHub 仓库

1. 登录你的 GitHub 账号
2. 点击右上角 **+** → **New repository**
3. 填写仓库名称，例如 `smart-farming-dashboard`
4. 选择 **Public**（GitHub Pages 免费版需要公开仓库）
5. 点击 **Create repository**

### 步骤2：上传代码

将本项目的所有文件上传到仓库中：

```bash
git clone https://github.com/你的用户名/smart-farming-dashboard.git
cd smart-farming-dashboard
# 将所有文件复制到该目录
git add .
git commit -m "Initial commit"
git push origin main
```

或者直接在 GitHub 网页上逐个文件创建（适合不熟悉 Git 的用户）。

### 步骤3：配置 GitHub Secrets

进入仓库页面 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**，依次添加以下3个 Secret：

| Secret 名称 | 说明 | 示例值 |
|---|---|---|
| `LARK_APP_ID` | 飞书开放平台 App ID | `cli_xxxxxxxx` |
| `LARK_APP_SECRET` | 飞书开放平台 App Secret | `xxxxxxxxxxxxxxxx` |
| `LARK_BASE_TOKEN` | 飞书 Base Token | `Oi1ObtIzLa7U8issGOGcO4JSneg` |

> **如何获取飞书凭证？**
> 1. 访问 [飞书开放平台](https://open.feishu.cn/)
> 2. 创建企业自建应用
> 3. 在「凭证与基础信息」中获取 App ID 和 App Secret
> 4. 在「权限管理」中开通 `bitable:record:read` 权限
> 5. 发布应用并获取 Base Token（在飞书 Base 的「设置」→「高级设置」中复制）

### 步骤4：修改表结构映射

编辑 `config/base_mapping.json`，根据你的飞书 Base 实际表结构修改：

```json
{
  "base_token": "你的Base Token",
  "tables": [
    {
      "name": "environment_params",
      "table_id": "你的表ID",
      "module": "环境趋势",
      "fields": ["record_time", "temperature", "humidity", "ammonia"],
      "description": "环境传感器数据"
    }
    // ... 其他表配置
  ]
}
```

> **如何获取 table_id？**
> 1. 打开飞书 Base
> 2. 在浏览器地址栏中查看 URL，格式为 `.../base/xxx?table=tblyyy`
> 3. `tblyyy` 即为 table_id

### 步骤5：开启 GitHub Pages

进入仓库页面 → **Settings** → **Pages**：

1. **Source**：选择 **Deploy from a branch**
2. **Branch**：选择 `gh-pages` → `/(root)`
3. 点击 **Save**

> 注意：首次配置后可能需要等待 2-3 分钟才能访问。

### 步骤6：手动触发首次构建

进入仓库页面 → **Actions** → **Update Dashboard** → **Run workflow** → 点击 **Run workflow**

等待工作流执行完成（约 1-2 分钟），然后访问：

```
https://你的用户名.github.io/smart-farming-dashboard/
```

## 数据更新机制

- **定时触发**：每15分钟自动执行（通过 cron: `*/15 * * * *`）
- **手动触发**：可在 Actions 页面随时手动运行
- **更新内容**：工作流会重新拉取飞书 Base 数据，渲染 HTML，推送到 `gh-pages` 分支

## 常见问题

### Q1: GitHub Actions 执行失败，提示 "Failed to obtain tenant access token"

**原因**：飞书 App ID 或 App Secret 配置错误。

**排查**：
1. 确认 Secrets 名称完全匹配（区分大小写）
2. 确认 App ID 和 App Secret 没有多余空格
3. 确认飞书应用已发布（不是草稿状态）

### Q2: 页面显示空白或 "暂无数据"

**原因**：Base 表结构映射不匹配。

**排查**：
1. 检查 `config/base_mapping.json` 中的 `table_id` 是否正确
2. 检查 `fields` 列表中的字段名是否与 Base 中完全一致（区分大小写）
3. 查看 Actions 日志中 `fetch_data.py` 的输出，确认拉取到的记录数

### Q3: 页面样式错乱

**原因**：GitHub Pages 部署路径问题。

**排查**：
1. 确认仓库是 Public 仓库
2. 确认 GitHub Pages 设置中的分支是 `gh-pages`
3. 清除浏览器缓存后刷新

### Q4: 如何修改数据更新频率？

编辑 `.github/workflows/update-dashboard.yml` 中的 cron 表达式：

```yaml
schedule:
  - cron: '*/15 * * * *'   # 每15分钟
  - cron: '0 * * * *'      # 每小时
  - cron: '0 0 * * *'      # 每天0点
```

> GitHub Actions 的定时触发可能有 5-15 分钟的延迟，不适合需要秒级实时更新的场景。

### Q5: 数据安全如何保障？

- ✅ API 凭证仅存储在 GitHub Secrets 中，代码和日志中不会暴露
- ✅ 生成的 HTML 是纯静态页面，不包含任何凭证信息
- ✅ 建议将 GitHub 仓库设为 Private（但 GitHub Pages 免费版需 Public）
- ⚠️ 飞书 Base 数据会嵌入到 HTML 中，任何人可以访问页面 URL 查看数据

## 技术栈

- **CI/CD**：GitHub Actions
- **托管**：GitHub Pages
- **数据拉取**：Python + Requests + 飞书 OpenAPI
- **模板渲染**：Jinja2
- **图表**：ECharts 5.6.0（CDN）
- **样式**：原生 CSS（无框架依赖）

## 自定义开发

### 添加新的数据模块

1. 在 `config/base_mapping.json` 中添加新的表配置
2. 在 `scripts/fetch_data.py` 中添加数据处理函数
3. 在 `template/dashboard.html.j2` 中添加对应的图表区域
4. 在 `.github/workflows/update-dashboard.yml` 中确保新文件被正确部署

### 修改页面样式

直接编辑 `template/dashboard.html.j2` 中的 CSS 变量和样式规则：

```css
:root {
  --bg-primary: #0a1628;     /* 主背景色 */
  --bg-card: #111d32;        /* 卡片背景色 */
  --accent-blue: #3b82f6;    /* 主色调 */
}
```

## License

MIT License
