# 模型文件说明

如需提升动漫人脸检测效果，可以把 `lbpcascade_animeface.xml` 放到本目录。

程序会优先读取：

1. `models/lbpcascade_animeface.xml`
2. OpenCV 自带的 `haarcascade_frontalface_default.xml`
3. 居中区域估算方案

因此没有额外模型文件时，项目仍然可以启动，但识别准确率会受图片构图影响。
