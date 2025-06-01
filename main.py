#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
#import requests
from typing import Optional, List
import asyncio
import httpx
from astrbot.api.all import *
from bilibili_api import video, HEADERS, Credential
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from bcut_asr import BcutASR
from bcut_asr.orm import ResultStateEnum
#from pyffmpeg import FFmpeg
#import json


async def bili_request(url, return_json=True):
    """发送B站API请求"""
    headers = {
        "referer": "https://www.bilibili.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            if return_json:
                return response.json()
            else:
                return response.content
    except (httpx.HTTPError, httpx.RequestError) as e:
        return {"code": -400, "message": str(e)}

@register("bilisum", "victical", "B站视频点评插件", "0.07", "https://github.com/victical/astrbot_plugin_bilisum")
class BiliSumPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        # 初始化插件数据目录
        data_path = context.get_config().get("data_path", "data")
        self.data_dir = os.path.join(data_path, "bilisum")
        # 创建临时文件目录
        self.temp_dir = os.path.join(self.data_dir, "temp")
        # 创建字幕文件目录
        self.subtitle_dir = os.path.join(self.data_dir, "subtitles")
        # 创建视频文件目录
        self.video_dir = os.path.join(self.data_dir, "videos")
        # 创建音频文件目录
        self.audio_dir = os.path.join(self.data_dir, "audios")
        
        # 确保所有目录都存在
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.subtitle_dir, exist_ok=True)
        os.makedirs(self.video_dir, exist_ok=True)
        os.makedirs(self.audio_dir, exist_ok=True)

        # 硬编码提示词模板
        self.prompt_template = "请以B站网友的视角，用轻松活泼的语气对视频进行简短点评，控制在50字以内。\n\n视频标题：{title}\n视频简介：{desc}\n视频内容：{content}"
        
        # 从配置中加载系统提示词
        if isinstance(config, dict):
            self.system_prompt = config.get("system_prompt", "你是一个B站资深用户，请用第一人称'我'来点评，就像在评论区留言一样。")
        else:
            self.system_prompt = "你是一个B站资深用户，请用第一人称'我'来点评，就像在评论区留言一样。"
        
        # 硬编码视频时长限制（12分钟）
        self.max_duration = 720

    def get_config(self):
        """获取当前配置"""
        return {
            "system_prompt": self.system_prompt
        }

    async def download_stream(self, url, headers, max_retries=3):
        """发送B站API请求"""
        headers = {
            "referer": "https://www.bilibili.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                return response
        except (httpx.HTTPError, httpx.RequestError) as e:
            return None

    async def get_best_subtitle(self, v, cid):
        try:
            # 获取视频信息
            info = await v.get_info()
            aid = info['aid']
            
            # 检查视频文件是否已存在
            video_download_path = os.path.join(self.data_dir, "videos", f"{v.get_bvid()}.mp4")
            if os.path.exists(video_download_path):
                logger.info(f"视频文件已存在: {video_download_path}")
                # 使用已存在的视频文件
                video_path = video_download_path
            else:
                # 使用bili_get的方法获取视频下载地址
                api_url = f"https://api.bilibili.com/x/player/playurl?avid={aid}&cid={cid}&qn=16&type=mp4&platform=html5"
                data = await bili_request(api_url)
                
                if data.get("code") != 0:
                    yield None, f"获取视频地址失败: {data.get('message')}"
                    return
                
                if not data.get("data", {}).get("durl"):
                    yield None, "视频没有可用的下载地址"
                    return
                    
                # 使用临时目录存放视频和音频文件
                video_path = os.path.join(self.temp_dir, f"{v.get_bvid()}_video.mp4")
                
                try:
                    # 下载视频流
                    video_url = data["data"]["durl"][0]["url"]
                    logger.info(f"开始下载视频流 (360p): {video_url}")
                    headers = HEADERS.copy()
                    headers.update({
                        'Referer': 'https://www.bilibili.com'
                    })
                    resp = await self.download_stream(video_url, headers)
                    
                    # 检查下载的内容
                    if not resp or not resp.content:
                        raise Exception("下载的视频内容为空")
                    
                    # 保存视频文件
                    with open(video_path, 'wb') as f:
                        f.write(resp.content)
                    
                    # 验证文件是否成功保存
                    if not os.path.exists(video_path):
                        raise Exception(f"视频文件保存失败: {video_path}")
                    
                    file_size = os.path.getsize(video_path)
                    logger.info(f"视频流下载完成，文件大小: {file_size} 字节")

                    # 移动视频文件到下载目录
                    os.makedirs(os.path.dirname(video_download_path), exist_ok=True)
                    import shutil
                    shutil.move(video_path, video_download_path)
                    logger.info(f"视频文件已保存到: {video_download_path}")
                    video_path = video_download_path

                except Exception as e:
                    logger.error(f"视频下载失败: {str(e)}")
                    if os.path.exists(video_path):
                        os.remove(video_path)
                    yield None, f"无法获取视频: {str(e)}"
                    return

            # 使用subprocess直接调用FFmpeg分离音频
            try:
                logger.info("开始分离音频...")
                
                # 检查输入文件
                if not os.path.exists(video_path):
                    raise Exception(f"输入视频文件不存在: {video_path}")
                
                # 检查音频文件是否已存在
                audio_path = os.path.join(self.audio_dir, f"{v.get_bvid()}.m4a")
                if os.path.exists(audio_path):
                    logger.info(f"音频文件已存在: {audio_path}")
                else:
                    # 使用subprocess直接调用FFmpeg
                    import subprocess
                    
                    # 使用确切的FFmpeg路径
                    ffmpeg_path = '/root/.pyffmpeg/bin/ffmpeg'
                    if not os.path.exists(ffmpeg_path):
                        raise Exception(f"FFmpeg不存在于路径: {ffmpeg_path}")
                    
                    # 使用临时目录存放临时音频文件
                    temp_audio_path = os.path.join(self.temp_dir, f"{v.get_bvid()}_audio.m4a")
                    
                    cmd = [
                        ffmpeg_path,
                        '-y',  # 覆盖已存在的文件
                        '-i', video_path,
                        '-vn',  # 禁用视频
                        '-acodec', 'aac',  # 使用AAC编码
                        '-ar', '44100',  # 设置采样率
                        '-ac', '2',  # 设置声道数
                        '-b:a', '192k',  # 设置比特率
                        '-loglevel', 'error',  # 只显示错误信息
                        temp_audio_path
                    ]
                    
                    # 使用Popen来执行命令
                    process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        universal_newlines=True
                    )
                    
                    # 等待进程完成
                    return_code = process.wait()
                    
                    if return_code != 0:
                        _, stderr = process.communicate()
                        raise Exception(f"FFmpeg执行失败 (返回码: {return_code}): {stderr}")
                    
                    # 验证输出文件
                    if not os.path.exists(temp_audio_path):
                        raise Exception(f"音频文件生成失败: {temp_audio_path}")
                    
                    # 移动音频文件到正式目录
                    import shutil
                    shutil.move(temp_audio_path, audio_path)
                    logger.info(f"音频文件已保存到: {audio_path}")
                
                audio_size = os.path.getsize(audio_path)
                logger.info(f"音频文件大小: {audio_size} 字节")
                
            except Exception as e:
                logger.error(f"音频分离失败: {str(e)}")
                if os.path.exists(temp_audio_path):
                    os.remove(temp_audio_path)
                raise Exception(f"音频分离失败: {str(e)}")

            # 使用必剪API识别字幕
            logger.info("开始识别字幕")
            asr = BcutASR(audio_path)
            asr.upload()
            asr.create_task()

            # 轮询检查结果
            while True:
                result = asr.result()
                if result.state == ResultStateEnum.COMPLETE:
                    break
                await asyncio.sleep(1)

            # 解析字幕内容
            subtitle = result.parse()
            if not subtitle.has_data():
                yield None, "字幕识别失败或内容为空"
                return

            # 保存字幕到字幕目录
            subtitle_path = os.path.join(self.subtitle_dir, f"{v.get_bvid()}_subtitle.txt")
            with open(subtitle_path, "w", encoding="utf-8") as f:
                f.write(subtitle.to_txt())
            logger.info(f"字幕已保存到: {subtitle_path}")

            yield subtitle, subtitle_path
            return
        except Exception as e:
            logger.error(f"获取字幕失败: {str(e)}")
            yield None, f"获取字幕失败: {str(e)}"
            return

    def _empty(self):
        pass

    @llm_tool(name="video-review")
    async def video_review(self, event: AstrMessageEvent, message: str = "") -> str:
        """
        对B站视频进行点评。当用户需要点评视频时，调用此函数。
        函数会自动识别消息中的B站视频链接或BV号，下载视频，提取字幕，并生成点评。

        Args:
            message (string): 用户的消息内容

        Returns:
            string: 生成的视频点评或错误信息
        """
        try:
            # 提取BVID
            import re
            bvid_match = re.search(r'BV\w+', message)
            if not bvid_match:
                return "请在消息中包含B站视频的BV号"

            bvid = bvid_match.group()

            # 创建视频对象
            v = video.Video(bvid=bvid)
            
            # 获取视频信息
            info = await v.get_info()
            title = info['title']
            
            # 检查视频时长
            duration = info.get('duration', 0)
            if duration > self.max_duration:
                return f"视频《{title}》时长超过{self.max_duration//60}分钟（{duration//60}分{duration%60}秒），请选择更短的视频"
            
            # 获取 cid
            cid = info['cid']

            # 获取最佳字幕
            subtitle = None
            subtitle_path = None
            async for subtitle, result in self.get_best_subtitle(v, cid):
                if subtitle is None:
                    return f"视频《{title}》字幕获取失败: {result}"
                subtitle_path = result

            # 构建提示词
            prompt = self.prompt_template.format(
                title=title,
                desc=info.get('desc', '无简介'),
                content=subtitle.to_txt() if subtitle and subtitle.has_data() else "注意：由于无法获取视频字幕，请仅根据标题和简介进行点评。"
            )
            
            # 调用LLM进行总结
            provider = self.context.get_using_provider()
            if provider:
                req = event.request_llm(
                    prompt=prompt,
                    session_id=None,
                    system_prompt=self.system_prompt
                )
                llm_response = await provider.text_chat(**req.__dict__)
                
                if llm_response.role == "assistant":
                    review_text = llm_response.completion_text
                    # 获取当前对话ID
                    conversation_id = await self.context.conversation_manager.get_curr_conversation_id(event.unified_msg_origin)
                    if not conversation_id:
                        conversation_id = await self.context.conversation_manager.new_conversation(event.unified_msg_origin)
                    
                    # 获取当前对话历史
                    conversation = await self.context.conversation_manager.get_conversation(event.unified_msg_origin, conversation_id)
                    history = json.loads(conversation.history) if conversation else []
                    
                    # 添加新的对话记录
                    history.append({"role": "user", "content": prompt})
                    history.append({"role": "assistant", "content": review_text})
                    
                    # 更新对话历史
                    await self.context.conversation_manager.update_conversation(
                        unified_msg_origin=event.unified_msg_origin,
                        conversation_id=conversation_id,
                        history=json.dumps(history)
                    )
                    return review_text
                else:
                    error_msg = f"视频点评失败：{llm_response.completion_text}"
                    # 获取当前对话ID
                    conversation_id = await self.context.conversation_manager.get_curr_conversation_id(event.unified_msg_origin)
                    if not conversation_id:
                        conversation_id = await self.context.conversation_manager.new_conversation(event.unified_msg_origin)
                    
                    # 获取当前对话历史
                    conversation = await self.context.conversation_manager.get_conversation(event.unified_msg_origin, conversation_id)
                    history = json.loads(conversation.history) if conversation else []
                    
                    # 添加错误信息到对话历史
                    history.append({"role": "user", "content": prompt})
                    history.append({"role": "assistant", "content": error_msg})
                    
                    # 更新对话历史
                    await self.context.conversation_manager.update_conversation(
                        unified_msg_origin=event.unified_msg_origin,
                        conversation_id=conversation_id,
                        history=json.dumps(history)
                    )
                    return error_msg
            else:
                error_msg = "未配置LLM提供商，无法进行视频点评"
                # 获取当前对话ID
                conversation_id = await self.context.conversation_manager.get_curr_conversation_id(event.unified_msg_origin)
                if not conversation_id:
                    conversation_id = await self.context.conversation_manager.new_conversation(event.unified_msg_origin)
                
                # 获取当前对话历史
                conversation = await self.context.conversation_manager.get_conversation(event.unified_msg_origin, conversation_id)
                history = json.loads(conversation.history) if conversation else []
                
                # 添加错误信息到对话历史
                history.append({"role": "user", "content": prompt})
                history.append({"role": "assistant", "content": error_msg})
                
                # 更新对话历史
                await self.context.conversation_manager.update_conversation(
                    unified_msg_origin=event.unified_msg_origin,
                    conversation_id=conversation_id,
                    history=json.dumps(history)
                )
                return error_msg

        except Exception as e:
            return f"处理视频时出错: {str(e)}"

    @llm_tool(name="process-video")
    async def process_video(self, event: AstrMessageEvent, bvid: str = "") -> str:
        """
        处理B站视频，包括下载视频、提取字幕和生成点评。

        Args:
            bvid (string): B站视频的BV号

        Returns:
            string: 处理结果
        """
        try:
            # 创建视频对象
            v = video.Video(bvid=bvid)
            
            # 获取视频信息
            info = await v.get_info()
            title = info['title']
            
            # 检查视频时长
            duration = info.get('duration', 0)
            if duration > self.max_duration:
                return f"视频《{title}》时长超过{self.max_duration//60}分钟（{duration//60}分{duration%60}秒），请选择更短的视频"
            
            # 获取 cid
            cid = info['cid']

            # 获取最佳字幕
            subtitle = None
            subtitle_path = None
            async for subtitle, result in self.get_best_subtitle(v, cid):
                if subtitle is None:
                    return f"视频《{title}》字幕获取失败: {result}"
                subtitle_path = result

            # 使用LLM总结字幕内容
            try:
                if subtitle and subtitle.has_data():
                    review = await self.video_review(event, subtitle.to_txt())
                else:
                    review = await self.video_review(event, "注意：由于无法获取视频字幕，请仅根据标题和简介进行点评。")
                
                return review
            except Exception as e:
                error_msg = f"视频点评失败: {str(e)}"
                if subtitle_path:
                    return f"视频《{title}》的字幕已保存到：{subtitle_path}\n注意：{error_msg}"
                else:
                    return f"视频《{title}》的字幕获取失败，且{error_msg}"

        except Exception as e:
            return f"处理视频时出错: {str(e)}"

    @filter.regex(r".*")
    async def handle_message(self, event: AstrMessageEvent):
        """处理所有消息，通过LLM识别是否需要处理视频"""
        try:
            # 获取当前对话ID
            conversation_id = await self.context.conversation_manager.get_curr_conversation_id(event.unified_msg_origin)
            if not conversation_id:
                conversation_id = await self.context.conversation_manager.new_conversation(event.unified_msg_origin)
            
            # 获取当前对话历史
            conversation = await self.context.conversation_manager.get_conversation(event.unified_msg_origin, conversation_id)
            history = json.loads(conversation.history) if conversation else []
            
            # 构建系统提示词
            system_prompt = """你是一个视频处理助手。当用户发送的消息中包含B站视频链接或BV号时，你需要：
1. 识别出视频的BV号
2. 调用process-video函数来处理视频
3. 如果消息中没有视频链接或BV号，则不做任何处理

请只返回JSON格式的响应，格式如下：
{
    "has_video": true/false,
    "bvid": "视频的BV号（如果有）",
    "message": "你的回复消息"
}"""

            # 调用LLM进行消息处理
            provider = self.context.get_using_provider()
            if provider:
                req = event.request_llm(
                    prompt=event.message_str,
                    session_id=None,
                    system_prompt=system_prompt
                )
                llm_response = await provider.text_chat(**req.__dict__)
                
                if llm_response.role == "assistant":
                    try:
                        response = json.loads(llm_response.completion_text)
                        if response.get("has_video", False) and response.get("bvid"):
                            # 处理视频
                            result = await self.process_video(event, response["bvid"])
                            yield event.set_result(MessageEventResult().message(result))
                        else:
                            # 不是视频相关消息，不做处理
                            return
                    except json.JSONDecodeError:
                        # LLM返回的不是有效的JSON，不做处理
                        return
                else:
                    # LLM调用失败，不做处理
                    return
            else:
                # 未配置LLM提供商，不做处理
                return

        except Exception as e:
            logger.error(f"处理消息时出错: {str(e)}")
            return
