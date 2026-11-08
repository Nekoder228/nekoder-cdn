"""Schedule queued carousels on TikTok through Zernio (audited TikTok partner).

queue/<id>/01.jpg..NN.jpg + post.json {"title","description","at" (ISO with offset), "music": true}
After a successful schedule a done.json is written next to it. Dirs whose time is >2 days past are removed.
Never prints the API key.
"""
import datetime as dt, json, os, shutil, sys, time, urllib.request, urllib.error

API = 'https://zernio.com/api/v1'
KEY = os.environ['ZERNIO_API_KEY'].strip()
SITE = 'https://nekoder228.github.io/nekoder-cdn/'
TZ = 'Europe/Bratislava'


def call(method, path, body=None):
    req = urllib.request.Request(API + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Authorization': 'Bearer ' + KEY, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw or b'{}')
        except Exception:
            return e.code, {'raw': raw[:500].decode('utf-8', 'replace')}


def tiktok_account():
    code, j = call('GET', '/accounts')
    accs = j.get('accounts', j.get('data', j if isinstance(j, list) else []))
    for a in accs:
        if a.get('platform') == 'tiktok':
            print('tiktok account:', a.get('username') or a.get('displayName'), '| active:', a.get('isActive', '?'))
            return a.get('_id') or a.get('id')
    print('no tiktok account connected. http', code, str(j)[:300])
    sys.exit(1)


def public(urls):
    for u in urls:
        for _ in range(40):
            try:
                with urllib.request.urlopen(urllib.request.Request(u, method='HEAD'), timeout=20) as r:
                    if r.status == 200:
                        break
            except Exception:
                pass
            time.sleep(15)
        else:
            print('not public yet:', u)
            sys.exit(1)


def main():
    now = dt.datetime.now(dt.timezone.utc)
    acc = None
    bad = 0
    for name in sorted(os.listdir('queue')):
        d = os.path.join('queue', name)
        meta_p = os.path.join(d, 'post.json')
        if not os.path.isfile(meta_p):
            continue
        meta = json.load(open(meta_p, encoding='utf-8'))
        at = dt.datetime.fromisoformat(meta['at']) if meta.get('at') else None
        if os.path.exists(os.path.join(d, 'done.json')):
            if at and now - at > dt.timedelta(days=2):
                shutil.rmtree(d)
                print('removed old', name)
            continue
        imgs = sorted(f for f in os.listdir(d) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')))
        urls = [SITE + d + '/' + f for f in imgs]
        public(urls)
        acc = acc or tiktok_account()
        body = {
            'content': meta.get('title', '')[:90],
            'mediaItems': [{'type': 'image', 'url': u} for u in urls],
            'platforms': [{'platform': 'tiktok', 'accountId': acc}],
            'tiktokSettings': {
                'privacy_level': meta.get('privacy', 'PUBLIC_TO_EVERYONE'),
                'allow_comment': True,
                'auto_add_music': meta.get('music', True),
                'photo_cover_index': 0,
                'description': meta.get('description', ''),
                'content_preview_confirmed': True,
                'express_consent_given': True,
            },
            'timezone': TZ,
        }
        if at and at > now + dt.timedelta(minutes=2):
            body['scheduledFor'] = meta['at']
        else:
            body['publishNow'] = True
        code, j = call('POST', '/posts', body)
        post = j.get('post', j)
        pid = post.get('_id') or post.get('id')
        if code in (200, 201, 207) and pid:
            print(name, '->', 'scheduled for ' + meta['at'] if 'scheduledFor' in body else 'published now', '| post', pid, '| status', post.get('status'))
            json.dump({'post_id': pid, 'status': post.get('status'), 'at': meta.get('at')}, open(os.path.join(d, 'done.json'), 'w'))
        else:
            print(name, 'error http', code, json.dumps(j, ensure_ascii=False)[:800])
            bad = 1
        time.sleep(5)
    sys.exit(bad)


if __name__ == '__main__':
    main()
