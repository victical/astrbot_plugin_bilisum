#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import requests
from typing import Optional, List
import asyncio
import httpx
from bilibili_api import video, HEADERS, Credential
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from bcut_asr import BcutASR
from bcut_asr.orm import ResultStateEnum
from pyffmpeg import FFmpeg

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

@register("bilisum", "victical", "B站视频字幕下载插件", "1.0.2", "https://github.com/victical/astrbot_plugin_bilisum")
class BiliSumPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 初始化插件数据目录
        data_path = context.get_config().get("data_path", "data")
        self.data_dir = os.path.join(data_path, "bilisum")
        # 创建临时文件目录
        self.temp_dir = os.path.join(self.data_dir, "temp")
        # 创建字幕文件目录
        self.subtitle_dir = os.path.join(self.data_dir, "subtitles")
        
        # 确保所有目录都存在
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.subtitle_dir, exist_ok=True)

        # 初始化凭证
        self.credential = Credential(
            sessdata="e4228576%2C1763999383%2C44db0%2A52CjCqpRBRlsPNRPjEiofD81cbyKoCEqGyfuFIWPR9NFQXRG--KGenVNhATH4r03I6-AYSVnRhamtBd3RialBTZnFsSjZxclgwS2dyUGVtNWVxUDBoM3RtUVlUd3BWTW1wTTAxb29FQnd4OVdBaEtEM0M2dzhXMU5IanZ3dG9NeGN3dFdBUlM5Z21BIIEC",
            bili_jct="dc46f9dad9a7c59fa5255dd0654ba8ff",
            buvid3="6C00639E-AF2D-EA94-F1B3-7E38A70A3A6052320infoc"
        )

    async def download_stream(self, url, headers, max_retries=3):
        for i in range(max_retries):
            try:
                async with httpx.AsyncClient() as client:
                    # 添加更多请求头
                    headers.update({
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                        'Accept': '*/*',
                        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'Origin': 'https://www.bilibili.com',
                        'Connection': 'keep-alive',
                        'Sec-Fetch-Dest': 'video',
                        'Sec-Fetch-Mode': 'cors',
                        'Sec-Fetch-Site': 'cross-site',
                        'Pragma': 'no-cache',
                        'Cache-Control': 'no-cache',
                        'Range': 'bytes=0-'
                    })
                    resp = await client.get(url, headers=headers, timeout=30.0)
                    if resp.status_code in [200, 206]:
                        return resp
                    logger.warning(f"下载失败，状态码：{resp.status_code}，第{i+1}次重试")
            except Exception as e:
                logger.warning(f"下载出错：{str(e)}，第{i+1}次重试")
            await asyncio.sleep(2)  # 增加重试间隔
        raise Exception(f"下载失败，已重试{max_retries}次")

    async def get_best_subtitle(self, v, cid):
        try:
            # 获取视频信息
            info = await v.get_info()
            aid = info['aid']
            
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
            audio_path = os.path.join(self.temp_dir, f"{v.get_bvid()}_audio.m4a")
            
            try:
                # 下载视频流
                video_url = data["data"]["durl"][0]["url"]
                logger.info(f"开始下载视频流: {video_url}")
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

                # 使用subprocess直接调用FFmpeg分离音频
                try:
                    logger.info("开始分离音频...")
                    
                    # 检查输入文件
                    if not os.path.exists(video_path):
                        raise Exception(f"输入视频文件不存在: {video_path}")
                    
                    # 使用subprocess直接调用FFmpeg
                    import subprocess
                    
                    # 使用确切的FFmpeg路径
                    ffmpeg_path = '/root/.pyffmpeg/bin/ffmpeg'
                    if not os.path.exists(ffmpeg_path):
                        raise Exception(f"FFmpeg不存在于路径: {ffmpeg_path}")
                    
                    logger.info(f"使用FFmpeg路径: {ffmpeg_path}")
                    
                    cmd = [
                        ffmpeg_path,
                        '-y',  # 覆盖已存在的文件
                        '-i', video_path,
                        '-vn',  # 禁用视频
                        '-acodec', 'aac',  # 使用AAC编码
                        '-ar', '44100',  # 设置采样率
                        '-ac', '2',  # 设置声道数
                        '-b:a', '192k',  # 设置比特率
                        audio_path
                    ]
                    
                    logger.info(f"执行FFmpeg命令: {' '.join(cmd)}")
                    
                    # 使用Popen来实时获取输出
                    process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        universal_newlines=True
                    )
                    
                    # 实时读取输出
                    while True:
                        output = process.stderr.readline()
                        if output == '' and process.poll() is not None:
                            break
                        if output:
                            logger.info(f"FFmpeg输出: {output.strip()}")
                    
                    # 获取返回码
                    return_code = process.poll()
                    
                    if return_code != 0:
                        _, stderr = process.communicate()
                        raise Exception(f"FFmpeg执行失败 (返回码: {return_code}): {stderr}")
                    
                    # 验证输出文件
                    if not os.path.exists(audio_path):
                        raise Exception(f"音频文件生成失败: {audio_path}")
                    
                    audio_size = os.path.getsize(audio_path)
                    logger.info(f"音频分离完成，文件大小: {audio_size} 字节")
                    
                except Exception as e:
                    logger.error(f"音频分离失败: {str(e)}")
                    if os.path.exists(audio_path):
                        os.remove(audio_path)
                    raise Exception(f"音频分离失败: {str(e)}")

                # 移动视频文件到下载目录而不是删除
                video_download_path = os.path.join(self.data_dir, "videos", f"{v.get_bvid()}.mp4")
                os.makedirs(os.path.dirname(video_download_path), exist_ok=True)
                if os.path.exists(video_path):
                    import shutil
                    shutil.move(video_path, video_download_path)
                    logger.info(f"视频文件已保存到: {video_download_path}")

            except Exception as e:
                logger.error(f"视频下载及音频分离失败: {str(e)}")
                if os.path.exists(video_path):
                    os.remove(video_path)
                if os.path.exists(audio_path):
                    os.remove(audio_path)
                yield None, f"无法获取视频音频: {str(e)}"
                return

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
                os.remove(audio_path)
                yield None, "字幕识别失败或内容为空"
                return

            # 保存字幕到字幕目录
            subtitle_path = os.path.join(self.subtitle_dir, f"{v.get_bvid()}_subtitle.txt")
            with open(subtitle_path, "w", encoding="utf-8") as f:
                f.write(subtitle.to_txt())
            logger.info(f"字幕已保存到: {subtitle_path}")

            # 清理临时文件
            os.remove(audio_path)

            yield subtitle, subtitle_path
            return
        except Exception as e:
            logger.error(f"获取字幕失败: {str(e)}")
            yield None, f"获取字幕失败: {str(e)}"
            return

    def _empty(self):
        pass

    @filter.command("bili")
    async def download_subtitle(self, event: AstrMessageEvent):
        try:
            # 获取命令参数
            message_obj = event.message_obj
            message = message_obj.message_str
            args = message.split()
            if len(args) != 2:
                yield event.set_result(MessageEventResult().message("请使用正确的格式：/bili <BVID>"))
                return

            bvid = args[1]
            if not bvid.startswith("BV"):
                yield event.set_result(MessageEventResult().message("请输入正确的 BVID，以 BV 开头"))
                return

            # 创建视频对象
            v = video.Video(bvid=bvid, credential=self.credential)
            
            # 获取视频信息
            info = await v.get_info()
            title = info['title']
            
            # 获取 cid
            cid = info['cid']

            # 获取最佳字幕
            async for subtitle, result in self.get_best_subtitle(v, cid):
                if subtitle is None:  # 如果subtitle为None，说明获取失败
                    yield event.set_result(MessageEventResult().message(f"视频《{title}》字幕获取失败: {result}"))
                    return
                subtitle_path = result  # 如果是成功，result就是subtitle_path

            # 使用LLM总结字幕内容
            try:
                provider = self.context.get_using_provider()
                if provider:
                    prompt = f"请对以下视频字幕内容进行总结，要求：1. 提取主要内容2. 总结核心观点3. 如果有重要数据或结论，请特别标注\n\n视频标题：{title}\n字幕内容：\n{subtitle.to_txt()}"
                    # 先发送字幕保存信息
                    yield event.set_result(MessageEventResult().message(f"视频《{title}》的字幕已保存到：{subtitle_path}"))
                    # 发送正在总结的提示
                    yield event.set_result(MessageEventResult().message("正在使用AI总结内容，请稍候..."))
                    # 调用LLM进行总结
                    req = event.request_llm(
                        prompt=prompt,
                        session_id=None,
                        system_prompt="你是一个专业的视频内容总结助手，擅长提取视频的核心内容和关键信息。"
                    )
                    llm_response = await provider.text_chat(**req.__dict__)
                    if llm_response.role == "assistant":
                        # 发送总结结果
                        yield event.set_result(MessageEventResult().message(f"内容总结：\n{llm_response.completion_text}"))
                    elif llm_response.role == "err":
                        yield event.set_result(MessageEventResult().message(f"内容总结失败：{llm_response.completion_text}"))
                else:
                    yield event.set_result(MessageEventResult().message(f"视频《{title}》的字幕已保存到：{subtitle_path}\n注意：未配置LLM提供商，无法进行内容总结"))
            except Exception as e:
                logger.error(f"LLM总结失败: {str(e)}")
                yield event.set_result(MessageEventResult().message(f"视频《{title}》的字幕已保存到：{subtitle_path}\n注意：内容总结失败: {str(e)}"))

        except Exception as e:
            logger.error(f"下载字幕时出错: {str(e)}")
            yield event.set_result(MessageEventResult().message(f"下载字幕时出错: {str(e)}"))