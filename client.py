import os
from util.common import resource_path
import socketio, ssl, websocket, requests, json, time
import base64
from http.cookies import SimpleCookie
from Audio import get_player
from login import LoginClient
import random
import string

class AudioSocketClient:
    MAX_LOG = 2000  # bytes/characters
    CLIENT_PING_SEC = 20  # 客戶端自送 keepalive，避免中間層(如 Nginx) 60s idle 斷線
    PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))

    def __init__(self, app_base, channel, username, password, gap_sec=1.0, cafile=None):
        self.app_base = app_base
        self.channel = channel
        self.username = username
        self.password = password
        self.gap_sec = gap_sec
        # Allow override via argument; otherwise use project root app.crt
        self.cafile = resource_path(cafile if cafile else os.path.join(self.PROJECT_ROOT, "app.crt"))

        self.player = get_player(gap_sec=self.gap_sec)
        self.client = LoginClient(app_base=self.app_base, username=self.username, password=self.password, ca_verify=self.cafile)
        self.TOKEN = self.client.get_token()

        self.AUTH_HEADERS = {
            "Authorization": f"Bearer {self.TOKEN}",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json",
        }

        self.ctx = ssl.create_default_context()
        self.ctx.load_verify_locations(cafile=self.cafile)  # 你的CA或server cert
        # 若你的 app.crt 沒有把 'localhost' 放在 SAN/CN，暫時關閉主機名檢查（測通路用，正式請發對的憑證）
        self.ctx.check_hostname = False
        # 讓 websocket-client 的 TLS 握手用這個 context
        websocket._default_ssl_context = self.ctx

        self.sio = socketio.Client(
            logger=False,
            engineio_logger=False,  # 暫時開啟，抓到真實錯誤位置（握手/升級/timeout）
            reconnection=True,
            reconnection_attempts=0,       # 無限次
            reconnection_delay=1,          # 1s 起跳
            reconnection_delay_max=5,      # 最長 5s
            ssl_verify=self.cafile,
        )

        # Register namespace and events
        self.sio.register_namespace(self.CatchAllNS(self, '/'))

        self.sio.on("PlayAudioEvent", handler=self._on_play_audio_generic)
        self.sio.on("reconnect_attempt", handler=self._on_reconnect_attempt)
        self.sio.on("reconnect", handler=self._on_reconnect)
        self.sio.on("reconnect_error", handler=self._on_reconnect_error)
        self.sio.on("error", handler=self._on_error)
        self.sio.on("server:pong", handler=self._on_server_pong)

        self.sio.on("connect", handler=self._on_connect)
        self.sio.on("connect_error", handler=self._on_connect_error)
        self.sio.on("disconnect", handler=self._on_disconnect)

        # Trust our self-signed/CA for HTTP polling requests used by Engine.IO
        self._ses = requests.Session()
        self._ses.verify = self.cafile  # use your CA/self-signed cert bundle
        self.sio.eio.http = self._ses

        # Optional: turn on websocket-client trace to see TLS/handshake errors
        try:
            websocket.enableTrace(True)
        except Exception:
            pass

    def _fmt(self, obj, key=None, limit=MAX_LOG):
        try:
            if isinstance(obj, (bytes, bytearray)):
                n = len(obj)
                head = obj[:limit]
                try:
                    head = head.decode('utf-8', 'ignore')
                except Exception:
                    head = str(head)
                return f"<bytes len={n} head={head[:120]!r}...>"
            if isinstance(obj, str):
                n = len(obj)
                head = obj[:limit]
                return head + (f"... <len={n}>" if n > limit else "")
            if isinstance(obj, dict):
                # redact common big fields
                redacted = {}
                for k, v in obj.items():
                    if k in ("audio", "pcm", "base64", "chunk", "buffer", "payload", "blob"):
                        if isinstance(v, (str, bytes, bytearray)):
                            redacted[k] = f"<{k} len={len(v)} redacted>"
                            continue
                    redacted[k] = v
                s = json.dumps(redacted, ensure_ascii=False)
                return s[:limit] + (f"... <len={len(s)}>" if len(s) > limit else "")
            # list/tuple
            if isinstance(obj, (list, tuple)):
                s = json.dumps(obj, ensure_ascii=False)
                return s[:limit] + (f"... <len={len(s)}>" if len(s) > limit else "")
            # fallback
            s = str(obj)
            return s[:limit] + (f"... <len={len(s)}>" if len(s) > limit else "")
        except Exception as e:
            return f"<fmt_err {e}>"

    def _on_connect(self):
        print("[OK] socket connected:", self.sio.sid)
        sub_payload = {
            "channel": self.channel,
            "auth": {
                "headers": {
                    # 只需要這幾個就夠了；視你的後端中介層而定
                    "Authorization": self.AUTH_HEADERS.get("Authorization"),
                    "Accept": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                }
            }
        }
        self.sio.emit("subscribe", sub_payload)
        print("[OK] subscribed", self.channel)

    class CatchAllNS(socketio.ClientNamespace):
        def __init__(self, outer, namespace):
            super().__init__(namespace)
            self.outer = outer

        def trigger_event(self, event, *args):
            try:
                head = args[0] if args else None
                print(f"[*] event={event} data={self.outer._fmt(head)}")
            except Exception:
                print(f"[*] event={event} (no data)")
            return super().trigger_event(event, *args)

    def _on_play_audio_generic(self, arg0=None, arg1=None):
        chan = arg0 if isinstance(arg0, str) else None
        payload = arg1 if isinstance(arg1, dict) else (arg0 if isinstance(arg0, dict) else {})

        if chan is not None and chan != self.channel:
            return  # ignore other channels

        self._handle_audio(payload)

    def _handle_audio(self, msg):
        if isinstance(msg, dict) and "data" in msg and isinstance(msg["data"], dict):
            msg = msg["data"]
        try:
            fmt = (msg or {}).get('format') or (msg or {}).get('mime')

            chunks = None
            if isinstance(msg, dict) and 'audio' in msg:
                a = msg.get('audio')
                if isinstance(a, dict):
                    try:
                        chunks = [a[k] for k in sorted(a.keys(), key=lambda x: int(x))]
                    except Exception:
                        chunks = list(a.values())
                elif isinstance(a, (list, tuple)):
                    chunks = list(a)

            if chunks:
                for b64 in chunks:
                    if isinstance(b64, (bytes, bytearray)):
                        b64 = b64.decode('utf-8', 'ignore')
                    if isinstance(b64, str) and b64:
                        self.player.enqueue_base64(b64, fmt)
                return

            b64 = (msg or {}).get('audio') or (msg or {}).get('base64')
            if isinstance(b64, (bytes, bytearray)):
                b64 = b64.decode('utf-8', 'ignore')
            if isinstance(b64, str) and b64:
                self.player.enqueue_base64(b64, fmt)
        except Exception as e:
            print("[handler-error broadcasting:message]", e)

    def _on_connect_error(self, data):
        print("[!] connect_error:", self._fmt(data))

    def _on_reconnect_attempt(self, attempt):
        print(f"[~] reconnect_attempt #{attempt}")

    def _on_reconnect(self, attempt):
        print(f"[OK] reconnected after #{attempt}")

    def _on_reconnect_error(self, err):
        print("[!] reconnect_error:", self._fmt(err))

    def _on_error(self, err):
        print("[!] error:", self._fmt(err))

    def _on_disconnect(self):
        print("[X] disconnected")

    def _on_server_pong(self, msg):
        print("[server:pong]", self._fmt(msg))

    def connect(self):
        try:
            print("Attempting Socket.IO connect via HTTPS (/socket.io)")
            self.sio.connect(
                self.app_base,
                headers=self.AUTH_HEADERS,
                socketio_path="/socket.io",
            )
        except Exception as e1:
            print("[connect] retry with trailing slash:", e1)
            self.sio.connect(
                self.app_base,
                headers=self.AUTH_HEADERS,
                socketio_path="/socket.io/",
            )

    def run_forever(self):
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.sio.disconnect()


if __name__ == "__main__":
    # Replace these placeholders with actual values before running
    APP_BASE = "https://tta-ad"
    CHANNEL = "private-audio.Lobby"
    USERNAME = "456456"
    PASSWORD = "456456"
    GAP_SEC = 1.0
    CAFILE = resource_path("app.crt")

    client = AudioSocketClient(APP_BASE, CHANNEL, USERNAME, PASSWORD, gap_sec=GAP_SEC, cafile=CAFILE)
    client.connect()
    client.run_forever()