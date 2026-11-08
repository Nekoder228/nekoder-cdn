"""TikTok Content Posting API helper (MEDIA_UPLOAD photo carousels to the creator's inbox).

Never prints tokens. State (refresh token) is kept AES-encrypted in state/token.enc on the `state` branch.
"""
import json, os, subprocess, sys, time, urllib.parse, urllib.request

API = 'https://open.tiktokapis.com'
KEY = os.environ['TIKTOK_CLIENT_KEY']
SECRET = os.environ['TIKTOK_CLIENT_SECRET']
REDIRECT = 'https://nekoder228.github.io/nekoder-cdn/callback.html'
SITE = 'https://nekoder228.github.io/nekoder-cdn/'
STATE = 'state/token.enc'


def http(method, url, data=None, headers=None, form=False):
    body = None
    h = dict(headers or {})
    if data is not None:
        if form:
            body = urllib.parse.urlencode(data).encode()
            h['Content-Type'] = 'application/x-www-form-urlencoded'
        else:
            body = json.dumps(data).encode()
            h['Content-Type'] = 'application/json; charset=UTF-8'
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b'{}')
        except Exception:
            return e.code, {}


def save_state(tok):
    os.makedirs('state', exist_ok=True)
    raw = json.dumps({'refresh_token': tok['refresh_token'], 'open_id': tok.get('open_id'), 'saved': int(time.time())})
    subprocess.run(['openssl', 'enc', '-aes-256-cbc', '-pbkdf2', '-salt', '-pass', 'env:TIKTOK_CLIENT_SECRET', '-out', STATE],
                   input=raw.encode(), check=True)


def load_state():
    out = subprocess.run(['openssl', 'enc', '-d', '-aes-256-cbc', '-pbkdf2', '-pass', 'env:TIKTOK_CLIENT_SECRET', '-in', STATE],
                         capture_output=True, check=True).stdout
    return json.loads(out)


def token_request(data):
    data = dict(data, client_key=KEY, client_secret=SECRET)
    code, j = http('POST', API + '/v2/oauth/token/', data, form=True)
    if code != 200 or 'access_token' not in j:
        print('token error:', code, j.get('error'), j.get('error_description'))
        sys.exit(1)
    for k in ('access_token', 'refresh_token'):
        print(f'::add-mask::{j[k]}')
    return j


def cmd_auth(code):
    j = token_request({'code': code, 'grant_type': 'authorization_code', 'redirect_uri': REDIRECT})
    save_state(j)
    print('authorized. scopes:', j.get('scope'), '| refresh valid days:', int(j.get('refresh_expires_in', 0)) // 86400)


def access_token():
    st = load_state()
    print(f"::add-mask::{st['refresh_token']}")
    j = token_request({'grant_type': 'refresh_token', 'refresh_token': st['refresh_token']})
    save_state(j)  # refresh token may rotate
    return j['access_token']


def wait_public(urls, tries=40):
    for u in urls:
        for i in range(tries):
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


def cmd_send(post_dir):
    meta = json.load(open(os.path.join(post_dir, 'post.json'), encoding='utf-8'))
    imgs = sorted(f for f in os.listdir(post_dir) if f.lower().endswith(('.jpg', '.jpeg', '.webp')))
    urls = [SITE + post_dir.strip('/') + '/' + f for f in imgs]
    print('post', os.path.basename(post_dir), 'slides', len(urls))
    wait_public(urls)
    tok = access_token()
    body = {
        'post_info': {'title': meta.get('title', '')[:90], 'description': meta.get('description', '')[:4000]},
        'source_info': {'source': 'PULL_FROM_URL', 'photo_cover_index': 0, 'photo_images': urls},
        'post_mode': 'MEDIA_UPLOAD',
        'media_type': 'PHOTO',
    }
    code, j = http('POST', API + '/v2/post/publish/content/init/', body, {'Authorization': 'Bearer ' + tok})
    err = j.get('error', {})
    if code != 200 or err.get('code') not in (None, 'ok'):
        print('init error:', code, err.get('code'), err.get('message'))
        sys.exit(1)
    pid = j['data']['publish_id']
    for i in range(60):
        time.sleep(10)
        code, s = http('POST', API + '/v2/post/publish/status/fetch/', {'publish_id': pid}, {'Authorization': 'Bearer ' + tok})
        st = s.get('data', {}).get('status')
        print('status:', st)
        if st in ('SEND_TO_USER_INBOX', 'PUBLISH_COMPLETE'):
            return
        if st == 'FAILED':
            print('fail reason:', s.get('data', {}).get('fail_reason'))
            sys.exit(1)
    print('timeout waiting for status')
    sys.exit(1)


if __name__ == '__main__':
    if sys.argv[1] == 'auth':
        cmd_auth(sys.argv[2])
    elif sys.argv[1] == 'send':
        cmd_send(sys.argv[2])
