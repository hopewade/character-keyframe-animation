# 播放器集成

`make_player.py` 根据 `sequence.json` 生成一个本地人物样稿，并复制技能内的 `character-player.js` 与 `.css`。默认产生相对路径的 `index.html`；脚本只覆盖它自身生成的样稿，不替换已有网站。加 `--embed` 同时生成内嵌帧、样式和脚本的 `preview.html`。这里的样稿只测试人物，不复制任何旧作品集的布局、文字或系统。

## 挂载到现有网页

复制播放器文件与已经补好的帧。使用以下组件结构，图片列表按清单生成，独立PNG中性回退图初始可见，帧图均加hidden：

```html
<section data-character-scene>
  <div data-keyframe-character>
    <div data-character-control role="img" tabindex="0"
         aria-label="人物随鼠标改变姿态，左右键切换姿态，Home键回到中性姿态">
      <div data-character-frames>
        <img data-character-poster src="poster.png" width="768" height="768" alt="">
        <!-- img data-character-frame="0" ...；每个索引对应清单的一张完整帧 -->
      </div>
    </div>
    <script type="application/json" data-character-sequence>
      {"positions":[-1,0,1],"frontFrame":1}
    </script>
  </div>
</section>
```

样例中的三项位置仅示意数据结构。实际应嵌入完整清单的位置和正确正面索引；每张图都有 `data-character-frame`，中性帧另加 `data-character-neutral`，独立中性PNG用 `data-character-poster`，正确设置宽高。运行脚本使用defer，或在DOM已存在后加载；JSON数据必须在初始化前出现。

播放器自动挂载所有 `[data-keyframe-character]`。也可调用 `mountKeyframeCharacter(root, {interactionTarget, damping:17})`，使用返回的 `setTarget(value)` 与 `dispose()`。转头默认监听当前 `[data-character-scene]` 区域；不应把所有页面点击解释成动作指令。

容器用 `--character-max-size` 和 `--character-ratio` 定义最大尺寸与原图比例。现有网页需根据文字、导航和窗口高度安排边距，保留完整服装。不要用负偏移或放大裁切替代布局适配。

## 默认交互契约

- 鼠标横向位置映射姿态位置，连续时间临界阻尼推进；中途改向保留速度，不按索引排队。
- 逐帧选择最近的预计算图；同一帧不重复画。每次绘制先清空Canvas，绝不同时显示两个DOM人物图层。
- 默认点击、双击和连点都不播放自动往返序列；方向键与Home仍可用。
- 预解码完成再启用动作；低动态偏好显示中性姿态。隐藏、离屏和原生dialog弹窗打开时暂停，恢复重设时钟。
- 自定义菜单或弹窗需要暂停时，在scene或其祖先设置 `data-character-paused="true"`，恢复时移除或设false。不要让旧人物控制器同时操作新Canvas或容器transform。
- 普通帧解码失败时显示独立PNG中性图；这也使WebP帧不可用时仍有静态回退。若PNG本身也无法加载，必须修复资源或展示清楚的替代文本，不能保证仍有人物可见。

默认实现适合一个短动作。多动作要定义各自的序列、共享中性帧及动作状态机；`setTarget()`不等于能够把不同动作素材任意连接。复杂循环需要先把尾帧回到相同中性姿态，再切序列。

## 实测

页面中检查 `data-ready`、`data-motion-state`、`data-position` 和 `data-frame` 可辅助诊断，但不能只看属性便宣布动画自然。浏览器真实移动鼠标、快速改向、停住、移出、连点和键盘后，观察真实画面。

检查桌面普通/短窗口、手机、屏幕DPR、动态偏好和资源加载失败。内存估算见补帧参考；独立GIF只用于看动作，不证明所有网页交互都正确。

当地预览、截图及交付遵循当前环境可用的网页/浏览器工具；不要擅自启用外部视频服务、上传角色照片或公开发布。

`--title` 设置样稿标题，`--label` 设置动作对应的无障碍说明。默认使用“改变姿态”，不把所有短动作都叫转头。小样最大尺寸不高于帧的原生尺寸；页面集成时也应避免盲目放大低清源图。
