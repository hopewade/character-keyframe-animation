# 毛线人物关键帧动画 Skill

把照片或已确认的角色设计，制作成一致的卡通人物，再通过**完整姿态关键帧 → 离线光流补帧 → 网页单 Canvas 逐帧播放**，实现自然转头和短动作。

适合毛线、针织等材质角色，也可用于其他卡通风格。这是预渲染二维动画流程；不需要建立三维模型或骨骼。

## 可以做什么

- 保持脸型、眼镜、发型、衣服和光照一致，设计角色及不同朝向的关键姿态。
- 在离线阶段生成透明 WebP 序列；先检查过渡，再输出全部帧。
- 鼠标位置控制朝向，支持左右方向键和 Home 回正，平滑处理快速改向。
- 每次只显示一张完整人物帧，避免前端多图叠加；包含静态回退和减少动效适配。
- 生成普通网页样稿，或将帧、样式和脚本内嵌到可离线打开的 HTML 中。

打字、思考、看简历等动作需要各自的有效关键姿态和共享的中性姿态；不能只靠转头素材推导复杂动作。

## 在 Codex 中安装与使用

首次安装时，将仓库放到个人 Skills 目录：

```bash
git clone https://github.com/hopewade/character-keyframe-animation.git ~/.codex/skills/character-keyframe-animation
```

如目标目录已经存在，先保留自己的修改，再选择合并或替换；不要直接覆盖。安装后在新会话中调用：

```text
使用 $character-keyframe-animation，参考我的照片制作毛线风格人物。
先确认形象，再制作完整头颈关键帧和随鼠标转头的动画。
```

角色图片通过当前环境的图像生成或编辑工具制作；此仓库不包含图像生成服务或 API 密钥。

## 运行辅助脚本

建议 Python 3.10 或更新版本。在仓库目录创建独立环境并安装依赖：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Windows 的环境激活命令为 `.venv\Scripts\activate`。

1. 准备同一角色、同尺寸、透明背景的完整姿态图，保留自然的头、脖子、领口和需要展示的衣服。
2. 参考 `references/sequence-config.json` 创建自己的配置。示例图片路径与坐标必须替换为当前角色的数据；仓库不附带人物源图。
3. 将源图和配置保留在生成目录以外。先输出少量过渡检查：

```bash
python scripts/build_sequence.py path/to/config.json --output path/to/animation --preview-only
```

4. 检查关键帧及过渡，尤其是瞳孔、眼镜、下颌、颈根、领口和透明边缘。确认后生成全部序列和播放器：

```bash
python scripts/build_sequence.py path/to/config.json --output path/to/animation
python scripts/make_player.py path/to/animation/sequence.json --embed
```

`index.html` 使用同目录资源；`preview.html` 内嵌所需帧、样式和脚本，可单独发送并在普通浏览器打开。生成脚本只覆盖它自身生成的样稿。

## 文件说明

| 文件 | 用途 |
| --- | --- |
| `SKILL.md` | Codex 技能入口及工作流程 |
| `references/character-design.md` | 人物一致性、毛线材质、关键姿态与动作衔接 |
| `references/interpolation-qa.md` | 光流补帧、透明边缘、质量检查及内存预算 |
| `references/player-integration.md` | 网页挂载、暂停恢复及交互约定 |
| `references/sequence-config.json` | 需要按角色替换的配置示例 |
| `scripts/build_sequence.py` | 生成补帧序列与检查预览 |
| `scripts/make_player.py` | 生成普通网页和单文件离线样稿 |
| `assets/player/` | 可复用的网页播放器 |

## 使用边界

增加帧数不能修复不一致的脸、眼镜或领口。离线补帧仍可能留下轮廓或纹理差异，必须检查实际图像与浏览器效果。

帧序列解码后的内存约为 `宽 × 高 × 4 × 帧数`，需要根据设备选择分辨率和帧数。本仓库不包含个人照片、已生成的私人头像或旧项目内容。
