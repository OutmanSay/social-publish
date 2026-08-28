#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
weibo_post.py — 发一条微博（纯 HTTP，读 Chrome「$WEIBO_CHROME_PROFILE」的登录 cookie，不需要开浏览器）。

用法:
  python3 weibo_post.py "正文内容"     # 发帖（仅在 用户确认后由 skill 调用）
  python3 weibo_post.py --check         # 只读自检：确认登录态还在（不发任何东西）

输出: 一行 JSON。发帖成功 -> {"ok":1,"url":...,"mblogid":...}；失败 -> {"ok":0,"error":...}

红线（见 SKILL.md）: 不 cron / 不自动发；每条必须 用户点头后才调本脚本。
依赖: browser_cookie3（pip install browser_cookie3）。
登录态: Chrome「$WEIBO_CHROME_PROFILE」登着 weibo.com 即可；脚本每次读最新 cookie，掉登录就重登一下。
"""
import sys, os, json, urllib.request, urllib.parse, urllib.error
import browser_cookie3

# 登着 weibo.com 的 Chrome Profile 目录名（Default / Profile 1 ...）和自己的微博 UID
PROFILE = os.environ.get('WEIBO_CHROME_PROFILE', 'Default')
PROFILE_COOKIES = os.path.expanduser(
    '~/Library/Application Support/Google/Chrome/%s/Cookies' % PROFILE)
UID = os.environ.get('WEIBO_UID', '')
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36')
MAX_LEN = 2000


def load_cookies():
    cj = browser_cookie3.chrome(cookie_file=PROFILE_COOKIES, domain_name='weibo.com')
    return {c.name: c.value for c in cj}


def _req(url, method='GET', body=None):
    cookies = load_cookies()
    xsrf = cookies.get('XSRF-TOKEN')
    if not cookies.get('SUB') or not xsrf:
        return None, {'ok': 0, 'error': '未登录或 cookie 缺失：请在 Chrome「$WEIBO_CHROME_PROFILE」里登录 weibo.com 后重试'}
    headers = {
        'user-agent': UA, 'referer': 'https://weibo.com/', 'accept': 'application/json',
        'x-xsrf-token': xsrf,
        'cookie': '; '.join('%s=%s' % (k, v) for k, v in cookies.items()),
    }
    data = None
    if body is not None:
        headers['content-type'] = 'application/x-www-form-urlencoded'
        data = urllib.parse.urlencode(body).encode('utf-8')
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=20)
        return json.loads(resp.read().decode('utf-8', 'ignore')), None
    except urllib.error.HTTPError as e:
        return None, {'ok': 0, 'error': 'HTTP %s: %s' % (e.code, e.read()[:200].decode('utf-8', 'ignore'))}
    except Exception as e:
        return None, {'ok': 0, 'error': '%s: %s' % (type(e).__name__, e)}


def check():
    if not UID:
        return {'ok': 0, 'error': '先设置环境变量 WEIBO_UID'}
    data, err = _req('https://weibo.com/ajax/statuses/mymblog?uid=%s&page=1&feature=0' % UID)
    if err:
        return err
    if data.get('ok') == 1:
        return {'ok': 1, 'logged_in': True, 'recent_posts': len((data.get('data') or {}).get('list') or [])}
    return {'ok': 0, 'error': '登录态失效（ok=%s）：请在 Chrome「$WEIBO_CHROME_PROFILE」重登 weibo.com' % data.get('ok')}


def list_posts(n=5):
    """只读：拉 自己最近 N 条微博的正文 + 链接（走登录态接口，公开页 / web_fetch 拿不到）。"""
    data, err = _req('https://weibo.com/ajax/statuses/mymblog?uid=%s&page=1&feature=0' % UID)
    if err:
        return err
    if data.get('ok') != 1:
        return {'ok': 0, 'error': '登录态失效（ok=%s）：请在 Chrome「$WEIBO_CHROME_PROFILE」重登 weibo.com' % data.get('ok')}
    posts = []
    for x in ((data.get('data') or {}).get('list') or [])[:n]:
        mid = x.get('mblogid') or x.get('idstr')
        posts.append({'created_at': x.get('created_at'), 'mblogid': mid,
                      'url': 'https://weibo.com/%s/%s' % (UID, mid),
                      'text': (x.get('text_raw') or x.get('text') or '')})
    return {'ok': 1, 'count': len(posts), 'posts': posts}


def post(content):
    data, err = _req('https://weibo.com/ajax/statuses/update', method='POST',
                     body={'content': content, 'visible': '0'})
    if err:
        return err
    if data.get('ok') == 1:
        d = data.get('data', {})
        mid = d.get('mblogid')
        return {'ok': 1, 'mblogid': mid, 'url': 'https://weibo.com/%s/%s' % (UID, mid),
                'created_at': d.get('created_at')}
    return {'ok': 0, 'error': data.get('msg') or data.get('error') or json.dumps(data, ensure_ascii=False)[:200]}


if __name__ == '__main__':
    args = sys.argv[1:]
    execute = '--execute' in args          # R4-5：不可逆发帖需显式 --execute
    args = [a for a in args if a != '--execute']
    if args and args[0] == '--check':
        out = check()
    elif args and args[0] == '--list':
        n = int(args[1]) if len(args) > 1 and args[1].isdigit() else 5
        out = list_posts(n)
    elif args and args[0].strip() and not args[0].startswith('--'):
        text = args[0]
        if len(text) > MAX_LEN:
            out = {'ok': 0, 'error': '正文过长（%d>%d 字）' % (len(text), MAX_LEN)}
        elif not execute:
            # R4-5：默认只预演不真发（微博发帖不可逆）。确认无误后加 --execute 才真正发送。
            out = {'ok': 1, 'dry_run': 1, 'preview': text, 'len': len(text),
                   'note': '预演，未发布。确认无误后加 --execute 真正发送。'}
        else:
            out = post(text)
    else:
        out = {'ok': 0, 'error': 'usage: weibo_post.py "正文" [--execute]  |  --check  |  --list [N]'}
    print(json.dumps(out, ensure_ascii=False))
    sys.exit(0 if out.get('ok') == 1 else 1)
