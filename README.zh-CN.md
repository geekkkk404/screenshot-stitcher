# screenshot-stitcher

[English](README.md) | [简体中文](README.zh-CN.md)

一个小而实用的 CLI，用来把多张纵向连续滚动的 iPhone 截图拼成一张长图。

它更适合同一台设备、同一页面流、按正确顺序输入的截图，尤其适合列表页、应用商店、设置页这类纵向界面。

## 成果展示

整理后的分组案例都放在 [`examples/cases/`](examples/cases) 目录下。

<table>
  <tr>
    <th align="left">案例</th>
    <th align="left">输入截图</th>
    <th align="left">拼接结果</th>
  </tr>
  <tr>
    <td><strong>App Store 搜索页</strong><br/>3 张截图<br/><a href="examples/cases/app-store-search/stitched.png">查看完整结果</a></td>
    <td><a href="examples/cases/app-store-search/preview-inputs.png"><img src="examples/cases/app-store-search/preview-inputs.png" width="360" alt="App Store 输入截图" /></a></td>
    <td><a href="examples/cases/app-store-search/stitched.png"><img src="examples/cases/app-store-search/preview-stitched.png" width="180" alt="App Store 拼接结果" /></a></td>
  </tr>
  <tr>
    <td><strong>小红书个人主页</strong><br/>3 张截图<br/><a href="examples/cases/xiaohongshu-profile/stitched.png">查看完整结果</a></td>
    <td><a href="examples/cases/xiaohongshu-profile/preview-inputs.png"><img src="examples/cases/xiaohongshu-profile/preview-inputs.png" width="360" alt="小红书个人主页输入截图" /></a></td>
    <td><a href="examples/cases/xiaohongshu-profile/stitched.png"><img src="examples/cases/xiaohongshu-profile/preview-stitched.png" width="180" alt="小红书个人主页拼接结果" /></a></td>
  </tr>
  <tr>
    <td><strong>Apple 官网首页</strong><br/>5 张截图<br/><a href="examples/cases/apple-homepage/stitched.png">查看完整结果</a></td>
    <td><a href="examples/cases/apple-homepage/preview-inputs.png"><img src="examples/cases/apple-homepage/preview-inputs.png" width="360" alt="Apple 官网首页输入截图" /></a></td>
    <td><a href="examples/cases/apple-homepage/stitched.png"><img src="examples/cases/apple-homepage/preview-stitched.png" width="180" alt="Apple 官网首页拼接结果" /></a></td>
  </tr>
</table>

## 功能

- 严格按你传入的顺序拼接截图
- 检测相邻截图的重叠区域，尽量避免重复内容
- 在重叠区选择更自然的水平切线，而不是简单硬切
- 支持通过参数调节顶部/底部 UI 裁剪和左右边缘屏蔽
- 在重叠置信度不足时，提供兜底拼接策略

## 安装

环境要求：

- Python `3.10` 或更新版本
- `pip`
- macOS、Linux 或 Windows，并且当前平台能安装预编译的 `opencv-python` wheel

这个项目推荐通过 `pip` 安装。

### 从 PyPI 安装

项目发布到 PyPI 后，推荐使用这种方式：

```bash
pip install screenshot-stitcher
screenshot-stitcher --help
```

如果机器上有多个 Python 环境，可以使用 `python -m pip`，确保安装到你要使用的那个 Python 环境：

```bash
python -m pip install screenshot-stitcher
```

### 从 GitHub 安装

如果还没有发布到 PyPI，可以直接从公开 GitHub 仓库安装：

```bash
pip install "git+https://github.com/mate-matt/screenshot-stitcher.git"
screenshot-stitcher --help
```

### 从已克隆的仓库安装

如果 Codex、Claude 这类 agent 已经在这个仓库目录里工作，直接在仓库根目录安装：

```bash
cd /path/to/screenshot-stitcher
pip install .
screenshot-stitcher --help
```

本地开发时可以使用 editable install：

```bash
pip install -e .
python main.py --help
```

安装后可以用内置示例快速验证：

```bash
screenshot-stitcher \
  examples/cases/app-store-search/inputs/01.png \
  examples/cases/app-store-search/inputs/02.png \
  examples/cases/app-store-search/inputs/03.png \
  -o /tmp/app-store-search-stitched.png
```

## 使用方式

```bash
screenshot-stitcher img1.png img2.png img3.png -o output.png
```

也可以直接运行仓库里的入口文件：

```bash
python main.py img1.png img2.png img3.png -o output.png
```

常用参数：

- `--top-crop`：手动指定顶部裁剪像素
- `--bottom-crop`：手动指定底部裁剪像素
- `--no-navbar`：页面没有导航栏时使用
- `--no-tabbar`：页面没有底部 Tab bar 时使用
- `--x-margin`：匹配时左右各裁掉多少像素，默认 `40`
- `--template-height`：重叠检测使用的模板高度
- `--threshold`：接受重叠匹配的置信度阈值

## 当前适用范围

这个项目故意保持在一个比较窄但实用的范围里：

- 同一台 iPhone 的截图
- 只处理纵向滚动
- 所有输入图片宽度一致
- 图片顺序由用户自己控制

## 已知限制

- 高重复布局仍然可能影响重叠检测
- 临时弹窗、徽标、悬浮元素可能破坏原本可用的重叠区域
- 动态头部、浏览器底栏等场景，有时需要手动调 `--top-crop`、`--bottom-crop` 或 `--x-margin`
- 它不是一个通用全景图引擎，也不是任意图片拼接器

## Codex Skill

仓库里还提供了一个 Codex skill：[`skills/screenshot-stitcher/`](skills/screenshot-stitcher)，可以把“拼接截图”请求路由到这个 CLI，并根据页面类型建议合适参数。

因为这个 CLI 的调用约定很简单、提示词表面也很薄，所以同样的 skill 模式也适合快速接到 Claude、Codex、OpenClaw、Hermes 以及类似的 agent 工具链里。

## 开发说明

- `examples/cases/`：README 里成功案例展示使用的素材
- `scripts/build_showcase_assets.py`：用于重新生成展示区的预览图

## License

[MIT](LICENSE)
