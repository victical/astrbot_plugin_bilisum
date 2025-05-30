#!/usr/bin/env python
# -*- coding: utf-8 -*-
import asyncio
import os
from typing import Optional, List

import httpx
from bilibili_api import video, HEADERS, Credential
from requests import Session

from langup.api.bilibili.schema import BiliNoteView

session = Session()
session.trust_env = False


class Video:
    def __init__(self, bvid: str, credential: Credential = None):
        self.bvid = bvid
        self.credential = credential
        self.__info = None
        self.__bn_info = None
        self.video = bilibili_api.Video(bvid=bvid, credential=credential)

    async def get_info(self):
        """获取视频信息"""
        if not self.__info:
            self.__info = await self.video.get_info()
        return self.__info

    async def get_subtitle_datalist(self):
        """获取字幕列表"""
        try:
            # 获取字幕列表
            subtitle_list = await self.video.get_subtitle_list(self.credential)
            print("字幕列表:", subtitle_list)
            
            if not subtitle_list:
                print("该视频没有字幕")
                return None
                
            # 优先选择中文（中国）字幕
            selected_subtitle = None
            for subtitle in subtitle_list:
                if subtitle['lan'] == 'zh-CN':
                    selected_subtitle = subtitle
                    break
                    
            # 如果没有中文（中国）字幕，选择中文（简体）
            if not selected_subtitle:
                for subtitle in subtitle_list:
                    if subtitle['lan'] == 'zh-Hans':
                        selected_subtitle = subtitle
                        break
                        
            # 如果还是没有，选择第一个可用的字幕
            if not selected_subtitle and subtitle_list:
                selected_subtitle = subtitle_list[0]
                
            if not selected_subtitle:
                print("没有找到可用的字幕")
                return None
                
            print("选择的字幕:", selected_subtitle)
            
            # 获取AI字幕列表
            ai_subtitle_list = await self.video.get_subtitle_list(self.credential, is_ai=True)
            print("AI字幕列表:", ai_subtitle_list)
            
            # 在AI字幕列表中查找对应的字幕
            if ai_subtitle_list:
                for ai_subtitle in ai_subtitle_list:
                    if ai_subtitle['id'] == selected_subtitle['id']:
                        selected_subtitle = ai_subtitle
                        break
            
            if not selected_subtitle.get('subtitle_url'):
                print("字幕URL为空")
                return None
                
            # 获取字幕内容
            subtitle_url = selected_subtitle['subtitle_url']
            if not subtitle_url.startswith('http'):
                subtitle_url = 'https:' + subtitle_url
                
            async with httpx.AsyncClient() as client:
                response = await client.get(subtitle_url)
                if response.status_code == 200:
                    subtitle_data = response.json()
                    return subtitle_data
                else:
                    print(f"获取字幕内容失败: {response.status_code}")
                    return None
                    
        except Exception as e:
            print(f"获取字幕列表失败: {str(e)}")
            return None

    async def download_audio(self, file_path):
        if os.path.exists(file_path + 'm4s.mp3'):
            return file_path + 'm4s.mp3'
        # 获取视频下载链接
        download_url_data = await self.get_download_url(0)
        # 解析视频下载信息
        detecter = video.VideoDownloadURLDataDetecter(data=download_url_data)
        streams = detecter.detect_best_streams()
        # 有 MP4 流 / FLV 流两种可能
        if detecter.check_flv_stream() == True:
            file_path += 'flv.mp3'
        else:
            file_path += 'm4s.mp3'
        # MP4 流下载
        await self.download_url(streams[1].url, file_path, "音频流")
        return file_path

    @staticmethod
    async def download_url(url: str, out: str, info: str):
        # 下载函数
        async with httpx.AsyncClient(headers=HEADERS) as sess:
            resp = await sess.get(url)
            length = resp.headers.get('content-length')
            with open(out, 'wb') as f:
                process = 0
                for chunk in resp.iter_bytes(1024):
                    if not chunk:
                        break
                    process += len(chunk)
                    # print(f'下载 {info} {process} / {length}')
                    f.write(chunk)

    @property
    def info(self) -> BiliNoteView:
        assert self.__info
        if not self.__bn_info:
            self.__bn_info = BiliNoteView(**self.__info)
        return self.__bn_info


async def main():
    # 创建认证信息
    credential = Credential(
        sessdata="e4228576%2C1763999383%2C44db0%2A52CjCqpRBRlsPNRPjEiofD81cbyKoCEqGyfuFIWPR9NFQXRG--KGenVNhATH4r03I6-AYSVnRhamtBd3RialBTZnFsSjZxclgwS2dyUGVtNWVxUDBoM3RtUVlUd3BWTW1wTTAxb29FQnd4OVdBaEtEM0M2dzhXMU5IanZ3dG9NeGN3dFdBUlM5Z21BIIEC",
        bili_jct="dc46f9dad9a7c59fa5255dd0654ba8ff",
        buvid3="6C00639E-AF2D-EA94-F1B3-7E38A70A3A6052320infoc"
    )
    
    # 创建视频对象
    v = Video(bvid="BV1GJ411x7h7", credential=credential)
    
    # 获取视频信息
    info = await v.get_info()
    print(f"标题: {info['title']}")
    print(f"UP主: {info['owner']['name']}")
    print(f"时长: {info['duration']}秒")
    print(f"播放量: {info['stat']['view']}")
    print(f"点赞数: {info['stat']['like']}")
    print(f"投币数: {info['stat']['coin']}")
    print(f"收藏数: {info['stat']['favorite']}")
    print(f"分享数: {info['stat']['share']}")
    print(f"弹幕数: {info['stat']['danmaku']}")
    print(f"评论数: {info['stat']['reply']}")
    print(f"封面: {info['pic']}")
    
    # 获取字幕
    subtitles = await v.get_subtitle_datalist()
    if subtitles:
        with open("subtitle.txt", "w", encoding="utf-8") as f:
            for subtitle in subtitles:
                try:
                    content = subtitle['content']
                    if isinstance(content, bytes):
                        content = content.decode('utf-8')
                    f.write(f"{subtitle['from']} -> {subtitle['to']}: {content}\n")
                except Exception as e:
                    print(f"处理字幕时出错: {e}")
                    continue
        print("字幕已保存到 subtitle.txt")
    else:
        print("该视频没有字幕")


if __name__ == '__main__':
    asyncio.run(main())