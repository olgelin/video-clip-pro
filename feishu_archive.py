#!/usr/bin/env python3
"""feishu_archive.py — 飞书输出归档模块

把 pipeline 产出自动备份到飞书：
  1. 成品文件（视频/BGM/歌词/元数据）上传到「AI 输出」文件夹，设组织内可读
  2. 往「AI 输出台账」多维表格 append 一行流水账（日期/任务/标题/标签/链接/耗时/状态）

用户手机飞书随时能看，实现"电脑一份 + 飞书一份"双备份。

用法：
  from feishu_archive import archive_task
  archive_task({
      'topic': '我把大脑剥离出来了',
      'mode': 'card',
      'title': '我把大脑剥离出来了',
      'tags': '思维模型 / AI',
      'video': 'output/.../final_polished.mp4',
      'bgm': 'output/.../bgm.wav',
      'lyrics': 'output/.../lyrics.txt',
      'cost': 1200,
      'status': '完成',
  })
"""
from __future__ import annotations
import requests, json, time
from pathlib import Path

# ── 飞书输出区配置（首次配置后固定）─────────────────────────
FOLDER_TOKEN = 'YdEvfDevSlF5O7dCXftcm8XCntD'   # 「AI 输出」文件夹
APP_TOKEN = 'YeCgbuWexaB56ds55Dicxpj4nSh'       # 「AI 输出台账」多维表格
TABLE_ID = 'tblNogBEMmGJcM9Y'                    # 台账数据表
ENV_PATH = Path('E:/Hermes-Agent/.env')

BASE = 'https://open.feishu.cn/open-apis'
UPLOAD_ALL_LIMIT = 20 * 1024 * 1024  # 飞书 upload_all 上限 20MB，超过走分片


def _load_env() -> dict:
    env = {}
    for line in ENV_PATH.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _get_token() -> str:
    env = _load_env()
    r = requests.post(f'{BASE}/auth/v3/tenant_access_token/internal',
                      json={'app_id': env['FEISHU_APP_ID'], 'app_secret': env['FEISHU_APP_SECRET']}, timeout=30)
    return r.json()['tenant_access_token']


def _set_public(token: str, typ: str = 'file') -> bool:
    """设链接分享为「组织内可读」，让同租户用户能通过链接访问。"""
    tok = _get_token()
    H = {'Authorization': f'Bearer {tok}', 'Content-Type': 'application/json'}
    body = {'external_access': True, 'security_entity': 'anyone_can_view',
            'comment_entity': 'anyone_can_view', 'share_entity': 'anyone',
            'link_share_entity': 'tenant_readable', 'invite_external': False}
    r = requests.patch(f'{BASE}/drive/v1/permissions/{token}/public?type={typ}',
                       headers=H, json=body, timeout=30)
    return r.json().get('code') == 0


def upload_file(local_path, folder_token: str = FOLDER_TOKEN, name: str = None) -> str | None:
    """上传文件到飞书输出区，设组织内可读，返回 file_url。小文件 upload_all，大文件分片。"""
    local = Path(local_path)
    if not local.exists():
        return None
    tok = _get_token()
    H = {'Authorization': f'Bearer {tok}'}
    file_name = name or local.name
    size = local.stat().st_size

    if size <= UPLOAD_ALL_LIMIT:
        url = _upload_all(local, file_name, folder_token, size, H)
    else:
        url = _upload_large(local, file_name, folder_token, size, H)
    return url


def _upload_all(local: Path, file_name: str, folder_token: str, size: int, H: dict) -> str | None:
    with open(local, 'rb') as f:
        files = {'file': (file_name, f)}
        data = {'file_name': file_name, 'parent_type': 'explorer',
                'parent_node': folder_token, 'size': str(size)}
        r = requests.post(f'{BASE}/drive/v1/files/upload_all', headers=H,
                          data=data, files=files, timeout=600)
    resp = r.json()
    if resp.get('code') != 0:
        print(f"      [feishu] 上传失败 {file_name}: {resp.get('msg')}")
        return None
    file_token = resp['data']['file_token']
    _set_public(file_token, 'file')
    return resp['data'].get('url', '')


def _upload_large(local: Path, file_name: str, folder_token: str, size: int, H: dict) -> str | None:
    """分片上传（>20MB 文件）。"""
    # 1. 准备上传
    r = requests.post(f'{BASE}/drive/v1/files/upload_prepare', headers={**H, 'Content-Type': 'application/json'},
                      json={'file_name': file_name, 'parent_type': 'explorer',
                            'parent_node': folder_token, 'size': size}, timeout=60)
    resp = r.json()
    if resp.get('code') != 0:
        print(f"      [feishu] 分片准备失败 {file_name}: {resp.get('msg')}")
        return None
    upload_id = resp['data']['upload_id']
    block_size = resp['data']['block_size']
    block_num = resp['data']['block_num']

    # 2. 逐片上传
    with open(local, 'rb') as f:
        for seq in range(block_num):
            block = f.read(block_size)
            files = {'file': (file_name, block)}
            data = {'upload_id': upload_id, 'seq': str(seq), 'size': str(len(block))}
            r = requests.post(f'{BASE}/drive/v1/files/upload_part', headers=H,
                              data=data, files=files, timeout=600)
            if r.json().get('code') != 0:
                print(f"      [feishu] 分片 {seq} 失败: {r.json().get('msg')}")
                return None

    # 3. 完成上传
    r = requests.post(f'{BASE}/drive/v1/files/upload_finish', headers={**H, 'Content-Type': 'application/json'},
                      json={'upload_id': upload_id, 'block_num': block_num}, timeout=60)
    resp = r.json()
    if resp.get('code') != 0:
        print(f"      [feishu] 分片完成失败: {resp.get('msg')}")
        return None
    file_token = resp['data']['file_token']
    _set_public(file_token, 'file')
    return resp['data'].get('url', '')


def add_record(fields: dict) -> bool:
    """往「AI 输出台账」append 一行记录。"""
    tok = _get_token()
    H = {'Authorization': f'Bearer {tok}', 'Content-Type': 'application/json'}
    r = requests.post(f'{BASE}/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/records',
                      headers=H, json={'fields': fields}, timeout=30)
    if r.json().get('code') != 0:
        print(f"      [feishu] 台账记录失败: {r.json().get('msg')}")
        return False
    return True


def _parse_tags(tags_raw) -> list:
    """标签统一成 list：支持 list / 逗号 / 顿号 / 斜杠分隔字符串。"""
    if not tags_raw:
        return []
    if isinstance(tags_raw, (list, tuple)):
        return [str(t).strip() for t in tags_raw if str(t).strip()]
    s = str(tags_raw).replace('，', ',').replace('、', ',').replace('/', ',').replace('／', ',')
    return [t.strip() for t in s.split(',') if t.strip()]


def archive_task(meta: dict) -> bool:
    """归档一次任务：上传成品 + 加台账记录（传媒公司精细化字段）。返回是否成功。"""
    topic = meta.get('topic', '')
    print(f"  [feishu] 归档任务「{topic}」...")

    video_url = upload_file(meta['video']) if meta.get('video') else None
    bgm_url = upload_file(meta['bgm']) if meta.get('bgm') else None
    lyrics_url = upload_file(meta['lyrics']) if meta.get('lyrics') else None

    tags = _parse_tags(meta.get('tags', []))

    fields = {
        '任务/主题': topic,                        # 主字段（飞书强制，不可删）
        '标题': meta.get('title', '') or topic,     # 成片标题
        '描述': meta.get('description', ''),         # 视频简介
        '管道': meta.get('mode', ''),               # 哪个管道
        '状态': meta.get('status', '完成'),
        '日期': int(time.time() * 1000),            # 毫秒时间戳
    }
    if tags:
        fields['标签'] = tags                       # 多选字段，传 list
    if video_url:
        fields['视频'] = {'text': '看视频', 'link': video_url}
    if bgm_url:
        fields['音乐'] = {'text': '背景音乐', 'link': bgm_url}

    # 输出结果 = 交付物清单
    parts = []
    if video_url:
        parts.append('视频')
    if bgm_url:
        parts.append('BGM')
    if lyrics_url:
        parts.append('歌词')
    fields['输出结果'] = ' + '.join(parts) if parts else '完成'

    ok = add_record(fields)
    if ok:
        print(f"  [feishu] ✅ 已归档到台账 + 输出区")
    return ok


if __name__ == '__main__':
    # 自测：归档一个测试任务
    ok = archive_task({
        'topic': '归档模块自测',
        'mode': 'card',
        'title': '归档模块自测',
        'tags': '测试',
        'cost': 10,
        'status': '完成',
    })
    print('结果:', '成功' if ok else '失败')
