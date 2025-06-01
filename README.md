# AstrBot B站视频点评插件

这是一个用于AstrBot的B站视频视频点评插件。该插件可以自动下载B站视频，提取字幕，并使用AI生成视频点评。
该插件全部由ai编写，使用前最好先备份astrbot，以免出现严重问题

## 功能特点

- 自动识别B站视频链接或BV号
- 下载视频并提取音频
- 使用必剪API进行语音识别，生成字幕
- 使用AI生成视频点评
- 支持对话历史记录
- 自动管理临时文件和缓存

## 系统要求

- Python 3.7+
- FFmpeg（用于音频处理）
- 必剪API（用于语音识别）

## 安装步骤

1. 安装FFmpeg：
   - Windows：
     ```bash
     # 使用chocolatey
     choco install ffmpeg
     # 或手动下载安装包并添加到系统PATH
     ```
   - Linux：
     ```bash
     sudo apt-get update
     sudo apt-get install ffmpeg
     ```

2. 安装Python依赖：
   ```bash
   pip install -r requirements.txt
   ```

3. 将插件目录复制到AstrBot的plugins目录下：
   ```
   AstrBot/data/plugins/astrbot_plugin_bilisum/
   ```

## 配置说明

插件支持以下配置选项：

```json
{
    "system_prompt": "你是一个B站资深用户，请用第一人称'我'来点评，就像在评论区留言一样。"
}
```

## 使用方法

1. 直接发送包含B站视频链接或BV号的消息，例如：
   ```
   帮我看看这个视频：https://www.bilibili.com/video/BVxxxxxx
   ```
   或
   ```
   点评一下这个视频：BVxxxxxx
   ```

2. 插件会自动：
   - 下载视频
   - 提取音频
   - 生成字幕
   - 使用AI生成视频点评

## 注意事项

- 视频时长限制为12分钟
- 需要确保FFmpeg正确安装并添加到系统PATH
- 建议使用较新版本的Python和依赖包

## 常见问题

1. 如果遇到"未找到ffmpeg"错误：
   - 确保FFmpeg已正确安装
   - 检查FFmpeg是否已添加到系统PATH
   - 可以手动指定FFmpeg路径

2. 如果字幕识别失败：
   - 检查网络连接
   - 确认视频音频质量
   - 查看必剪API是否可用
