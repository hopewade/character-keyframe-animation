# 角色与关键帧设计

## 形象确认

优先使用用户已认可的头像。照片用于身份参考；设计参考用于材质、比例和光照，不将参考网页人物的脸复制给用户。提取可见特征：脸型、发际与分缝、眼镜形状、眉眼间距、鼻和下颌、服装轮廓。卡通化程度由用户意图决定，不擅自改变性别表达或身体比例。

需要探索形象时先制作1—2个候选，并检查眼睛视线、左右瞳孔、眼镜结构、颈肩连接和服装；用户已有认可形象或授权自主选择时直接沿用该决定。先检查外形，之后再批量制作动作。新动作以同一认可角色图为参照，不用相互独立的新人物提示重新设计身份。

形象提示模板（将方括号替换为当前任务）：

> Create a [style/material] character based on the identity reference. Preserve [specific visible identity features]. Use [framing] with a complete head, both ears, a natural neck, collar and the required clothing visible. Keep natural anatomical proportions with [requested cartoon degree]. Use [lighting] and a true transparent background. No text, logos, props or scene unless requested.

关键帧提示模板：

> Edit this approved character into a [specific direction/gesture] key pose. Keep the exact same identity, eyes, glasses construction, hairstyle, clothing, material, light direction and camera. Lock the canvas size, scale, framing and shoulder/garment landmarks. Preserve the complete head-to-neck-to-collar connection in this image. Change only the requested pose. True alpha background; no added objects or text.

透明背景使用生成工具的透明参数；不能把棋盘格画进人物图当作透明。使用图像编辑工具前查看当前目标文件并遵循工具要求。生成工具不可用时可以整理已有素材或写实施方案，不能用临时拼装的人体几何体冒充同样的人物设计。

## 主关键姿态

转头：正面与适度的左右姿态先形成一组，必要时各加一张中间姿态。每张应有自然、完整的脖子和领口。实际检查角度的递增关系；一些“新增角度”可能几乎相同，不必全部保留。

其他短动作：先定义中性姿态、动作顶点与返回姿态。打字需要手、设备和肩颈共同合理；看简历需要纸张与视线对应；思考可包含托腮、向上看和小气泡，但应先由用户确定。构图不能在动作中忽然增加或删除本应一直存在的肢体或道具。

首尾相接：循环的第一帧与最后一帧应使用同一中性姿态。多动作串联时共享一个可复用的中性或交接姿态，先收回手和道具再进入下一动作。不要直接在两套不兼容构图间强行补帧。

复杂的遮挡、手指跨脸、突然出现道具等，通常需要更接近的真实关键帧。当前辅助脚本主要用于短距、同构图的转向和动作过渡；不能保证从极少帧推导复杂动作。

## 相机与角色对齐

先尽量在生成阶段锁定构图。需要相机校准时，只用衣服纽扣、肩部或颈根等稳定标记做受约束的等比缩放和平移；避免逐帧非等比拉伸。不要将转动的鼻尖固定在同一点，否则会把真实转向消掉。

若眼镜结构、发型轮廓或领口已经改变，应修正对应源图。补帧是连接有效姿态，不是替代身份一致性的修图器。
