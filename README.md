# 🧠 Stimulus Generator

<div align="center">

![版本](https://img.shields.io/badge/版本-1.0.0-blue)
![许可证](https://img.shields.io/badge/许可证-Apache%202.0-green)
![Python版本](https://img.shields.io/badge/Python-3.8+-yellow)
[![文档状态](https://img.shields.io/badge/文档-最新-brightgreen)](https://github.com/xufengduan/Stimuli_generator)

</div>

<p align="center">
  <b>基于大语言模型的心理语言学实验刺激材料生成工具</b>
</p>

---

## 📖 项目简介

Stimulus Generator 是一个基于大语言模型的刺激材料生成工具，专门为心理语言学研究设计。它能够根据研究者定义的实验设计和示例，自动生成符合要求的实验刺激材料。该工具采用多代理架构，包含生成器(Generator)、验证器(Validator)和评分器(Scorer)三个代理，确保生成的刺激材料满足实验要求并具有良好的质量。

## ✨ 主要特点

- **🤖 多代理架构**：
  - **Generator**：根据实验设计生成刺激材料
  - **Validator**：验证生成的材料是否符合实验要求
  - **Scorer**：对材料进行多维度评分

- **🔄 灵活的模型选择**：
  - 支持 GPT-4 (需要 OpenAI API Key)
  - 支持 Meta Llama 3.3 70B Instruct 模型

- **📊 实时进度监控**：
  - WebSocket 实时更新生成进度
  - 详细的日志信息显示
  - 可随时停止生成过程

- **🎨 用户友好界面**：
  - 直观的表单设计
  - 实时验证和反馈
  - 响应式布局设计
  - 详细的帮助信息提示

## 💻 系统要求

| 要求 | 详情 |
|------|------|
| Python | 3.8 或更高版本 |
| 浏览器 | 现代网页浏览器（Chrome、Firefox、Safari 等） |
| 网络 | 稳定的网络连接 |
| Socket.IO | 客户端版本 4.x（与服务器端兼容） |

## 🚀 安装说明

### 直接从GitHub仓库中克隆

```bash
# 1. 克隆项目代码
git clone https://github.com/xufengduan/Stimuli_generator.git
cd Stimuli_generator

# 2. 创建并激活虚拟环境（推荐）
python -m venv venv

# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate

# 3. 安装项目所需依赖
pip install -e .
```

## 📝 使用说明

### 启动Web界面

安装完成后，可以直接使用命令行工具启动Web界面：

```bash
stimulus-generator webui
```

默认情况下，Web界面将在 http://127.0.0.1:5000 上运行。

### 命令行参数

```bash
stimulus-generator webui --port 5001
```

| 参数 | 描述 |
|------|------|
| `--host` | 指定主机地址（默认：0.0.0.0） |
| `--port` | 指定端口号（默认：5001） |
| `--debug` | 启用调试模式 |
| `--share` | 创建公共链接（需要安装额外依赖） |

### 使用步骤

1. **配置生成参数**：
   - 选择使用的语言模型
   - 如使用 GPT-4，输入 OpenAI API Key
   - 填写实验设计说明
   - 添加示例刺激材料
   - 设置验证条件
   - 定义评分维度

2. **开始生成**：
   - 点击 "Generate stimulus" 按钮开始生成
   - 实时监控生成进度
   - 查看详细日志信息
   - 必要时可点击 "Stop" 按钮终止生成

3. **获取结果**：
   - 生成完成后自动下载 CSV 格式的结果文件
   - 结果文件包含生成的刺激材料及其评分

## 📂 文件结构

```
Stimulus-Generator/
├── stimulus_generator/    # 主Python包
│   ├── __init__.py        # 包初始化文件
│   ├── app.py             # Flask 后端服务器
│   ├── backend.py         # 后端核心功能
│   └── cli.py             # 命令行接口
├── run.py                 # 快速启动脚本
├── setup.py               # 包安装配置
├── static/
│   ├── script.js          # 前端 JavaScript 代码
│   ├── styles.css         # 页面样式表
│   └── Stimulus Generator Web Logo.png  # 网站图标
├── webpage.html           # 主页面
├── requirements.txt       # Python 依赖列表
└── README.md              # 项目说明文档
```

## 🛠️ 命令行工具

安装后，可以使用以下命令行工具：

```bash
# 启动Web界面
stimulus-generator webui [--host HOST] [--port PORT] [--debug] [--share]

# 查看帮助
stimulus-generator --help
```

如果您不想安装，也可以直接使用以下方式运行：

```bash
# 克隆仓库后，在项目目录中运行
python run.py webui
```

## ⚠️ 注意事项

1. **API 密钥安全**：
   - 请妥善保管您的 OpenAI API Key
   - 不要在公共环境中暴露 API Key

2. **生成过程**：
   - 生成过程可能需要一定时间，请耐心等待
   - 可以通过日志面板实时监控生成状态
   - 如遇到问题可以随时停止生成

3. **结果使用**：
   - 建议检查生成的材料是否符合实验要求
   - 可能需要对生成的材料进行人工筛选或修改

## ❓ 常见问题

<details>
<summary><b>生成过程卡住怎么办？</b></summary>
<br>
- 检查网络连接是否正常
- 点击 "Stop" 按钮停止当前生成
- 刷新页面重新开始
- 如果页面长时间无响应，可以等待30秒，系统会自动解除界面锁定
</details>

<details>
<summary><b>WebSocket连接错误如何解决？</b></summary>
<br>
- 确保网络环境没有阻止WebSocket连接
- 如果看到WebSocket错误信息，可以刷新页面重新建立连接
- 重启服务器或尝试使用不同的浏览器
- WebSocket连接问题不会影响主要功能，系统有自动恢复机制
</details>

<details>
<summary><b>如何优化生成质量？</b></summary>
<br>
- 提供更多详细的示例
- 完善实验设计说明
- 设置合适的验证条件
</details>

<details>
<summary><b>生成速度较慢怎么处理？</b></summary>
<br>
- 考虑减少生成数量
- 确保网络连接稳定
- 选择响应更快的模型
</details>

## 📞 技术支持

如有问题或建议，请通过以下方式联系：
- 提交 [Issue](https://github.com/xufengduan/Stimuli_generator/issues)
- 发送邮件至：...

## 📄 许可证

本项目采用 [Apache License 2.0](LICENSE) 许可证。详见 LICENSE 文件。 