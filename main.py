# main.py
import asyncio
import websockets
import json
import os
import secrets
from functools import partial
from datetime import datetime

PORT = int(os.environ.get("PORT", 8000))
HOST = "0.0.0.0"

CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUD_NAME", "your_cloud_name")
CLOUDINARY_UPLOAD_PRESET = os.environ.get("UPLOAD_PRESET", "your_preset")

# { code: { "ws": websocket, "name": str, "avatar": str, "typing": set() } }
online_users = {}

def generate_code():
    return secrets.token_urlsafe(4).replace("_", "").replace("-", "").upper()[:5]

# --- HTML مع دعم PWA ومؤشر الكتابة الكامل ---
HTML = '''
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>وَصِل</title>
    <meta name="description" content="دردشة فورية برقم فريد — بدون تسجيل">
    <link rel="manifest" href="/manifest.json">
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>💬</text></svg>">
    <style>
        :root {
            --bg: #ffffff;
            --text: #000000;
            --header: #075e54;
            --msg-bg: #dcf8c6;
            --input-bg: #f0f2f5;
            --border: #e0e0e0;
        }
        @media (prefers-color-scheme: dark) {
            :root {
                --bg: #121212;
                --text: #ffffff;
                --header: #064a43;
                --msg-bg: #2a3f35;
                --input-bg: #2a2a2a;
                --border: #444444;
            }
        }
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', Tahoma, sans-serif; }
        body {
            background: var(--bg);
            color: var(--text);
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        .header {
            background: var(--header);
            color: white;
            padding: 12px 15px;
            text-align: center;
            font-weight: bold;
            font-size: 18px;
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 10px;
        }
        .avatar {
            width: 36px;
            height: 36px;
            border-radius: 50%;
            object-fit: cover;
            background: #ddd;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            color: white;
        }
        .chat-area {
            flex: 1;
            display: flex;
            flex-direction: column;
            padding: 10px;
        }
        #chats {
            flex: 1;
            background: var(--input-bg);
            padding: 15px;
            border-radius: 12px;
            overflow-y: auto;
            margin-bottom: 15px;
            border: 1px solid var(--border);
        }
        .message {
            max-width: 70%;
            padding: 10px 14px;
            margin-bottom: 10px;
            border-radius: 12px;
            word-wrap: break-word;
        }
        .sent {
            background: var(--msg-bg);
            margin-left: auto;
        }
        .received {
            background: var(--border);
            margin-left: 0;
        }
        .file-msg {
            color: var(--header);
            text-decoration: underline;
            cursor: pointer;
        }
        .typing {
            color: #999;
            font-style: italic;
            padding: 5px 0;
            font-size: 14px;
        }
        .input-area {
            display: flex;
            gap: 8px;
            align-items: center;
        }
        #manualCode, #messageInput {
            padding: 12px;
            border: 1px solid var(--border);
            border-radius: 24px;
            font-size: 16px;
            outline: none;
            background: var(--input-bg);
            color: var(--text);
        }
        #manualCode { flex: 0 0 100px; text-align: center; }
        #messageInput { flex: 1; }
        .input-buttons {
            display: flex;
            gap: 6px;
        }
        .btn {
            background: var(--header);
            color: white;
            border: none;
            width: 36px;
            height: 36px;
            border-radius: 50%;
            font-size: 16px;
            cursor: pointer;
        }
        .info {
            text-align: center;
            padding: 8px;
            font-size: 13px;
            color: #666;
        }
        #yourLink {
            display: block;
            margin: 5px auto;
            padding: 6px;
            background: rgba(0,0,0,0.05);
            border-radius: 6px;
            font-size: 12px;
            color: var(--header);
            text-decoration: none;
            max-width: 90%;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .install-btn {
            background: #4CAF50;
            color: white;
            border: none;
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 12px;
            cursor: pointer;
            margin-top: 5px;
            display: none;
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="avatar" id="myAvatar">👤</div>
        وَصِل
        <button class="install-btn" id="installBtn">تثبيت التطبيق</button>
    </div>
    <div class="chat-area">
        <div id="chats">
            <div class="placeholder">جاري الاتصال...</div>
        </div>
        <div class="typing" id="typingIndicator" style="display:none;"></div>
        <div class="info">
            <a id="yourLink" href="#" target="_blank">يتم التحميل...</a>
        </div>
        <div class="input-area">
            <input type="text" id="manualCode" placeholder="كود" maxlength="10">
            <input type="text" id="messageInput" placeholder="اكتب رسالتك..." autocomplete="off" disabled>
            <div class="input-buttons">
                <input type="file" id="fileInput" style="display:none;" accept="*">
                <button class="btn" id="fileBtn">📎</button>
                <button class="btn" id="sendBtn" disabled>➤</button>
            </div>
        </div>
    </div>

    <script>
        // --- PWA Install Button ---
        let deferredPrompt;
        const installBtn = document.getElementById('installBtn');
        
        window.addEventListener('beforeinstallprompt', (e) => {
            e.preventDefault();
            deferredPrompt = e;
            installBtn.style.display = 'inline-block';
        });

        installBtn.addEventListener('click', () => {
            if (deferredPrompt) {
                deferredPrompt.prompt();
                deferredPrompt.userChoice.then((choiceResult) => {
                    if (choiceResult.outcome === 'accepted') {
                        console.log('تم تثبيت التطبيق');
                    }
                    installBtn.style.display = 'none';
                    deferredPrompt = null;
                });
            }
        });

        // --- باقي الكود ---
        const urlParams = new URLSearchParams(window.location.search);
        const targetCode = urlParams.get('c');
        let myCode = localStorage.getItem("myCode");
        let myName = localStorage.getItem("myName") || "";
        let myAvatar = localStorage.getItem("myAvatar") || null;
        let currentTargetCode = targetCode;
        let ws;
        const chats = {{}}; // { targetCode: [msgs] }

        const avatarDiv = document.getElementById("myAvatar");
        if (myAvatar) {{
            avatarDiv.innerHTML = `<img src="${{myAvatar}}" style="width:100%;height:100%;border-radius:50%;">`;
        }}

        if (!myName) {{
            myName = prompt("مرحباً! ما اسمك؟", "ضيف") || "ضيف";
            localStorage.setItem("myName", myName);
        }}

        const useAvatar = confirm("هل تريد رفع صورة شخصية؟");
        if (useAvatar) {{
            const input = document.createElement("input");
            input.type = "file";
            input.accept = "image/*";
            input.onchange = (e) => {{
                const file = e.target.files[0];
                if (file) {{
                    const reader = new FileReader();
                    reader.onload = () => {{
                        myAvatar = reader.result;
                        localStorage.setItem("myAvatar", myAvatar);
                        avatarDiv.innerHTML = `<img src="${{myAvatar}}" style="width:100%;height:100%;border-radius:50%;">`;
                    }};
                    reader.readAsDataURL(file);
                }}
            }};
            input.click();
        }} else {{
            const initials = (myName[0] || '👤') + (myName[1] || '');
            avatarDiv.innerText = initials;
            avatarDiv.style.backgroundColor = '#075e54';
        }}

        ws = new WebSocket("wss://" + window.location.host + "/ws");
        const chatsDiv = document.getElementById("chats");
        const messageInput = document.getElementById("messageInput");
        const sendBtn = document.getElementById("sendBtn");
        const fileBtn = document.getElementById("fileBtn");
        const fileInput = document.getElementById("fileInput");
        const manualCodeInput = document.getElementById("manualCode");
        const typingIndicator = document.getElementById("typingIndicator");
        const yourLink = document.getElementById("yourLink");

        ws.onopen = () => {{
            ws.send(JSON.stringify({{
                myCode: myCode,
                myName: myName,
                myAvatar: myAvatar
            }}));
        }};

        ws.onmessage = (event) => {{
            const data = JSON.parse(event.data);
            
            if (data.type === "init") {{
                myCode = data.myCode;
                localStorage.setItem("myCode", myCode);
                const fullLink = `${{window.location.origin}}?c=${{myCode}}`;
                yourLink.href = fullLink;
                yourLink.innerText = "شارك رابط دردشتك:";
                yourLink.title = fullLink;

                if (targetCode) {{
                    currentTargetCode = targetCode;
                    enableChat(targetCode);
                }}
            }}

            if (data.type === "message") {{
                const fromCode = data.fromCode;
                const content = data.content;
                const isFile = data.isFile;
                addMessageToChat(fromCode, content, false, isFile);
                if (currentTargetCode === fromCode) {{
                    scrollToBottom();
                }}
            }}

            if (data.type === "typing") {{
                const fromCode = data.fromCode;
                if (currentTargetCode === fromCode) {{
                    if (data.isTyping) {{
                        typingIndicator.innerText = "يكتب...";
                        typingIndicator.style.display = "block";
                    } else {{
                        typingIndicator.style.display = "none";
                    }}
                }}
            }}
        }};

        // --- مؤشر الكتابة (مرتبط بكل محادثة) ---
        let typingTimer;
        messageInput.oninput = () => {{
            if (currentTargetCode) {{
                ws.send(JSON.stringify({{ 
                    type: "typing", 
                    toCode: currentTargetCode, 
                    isTyping: true 
                }}));
                clearTimeout(typingTimer);
                typingTimer = setTimeout(() => {{
                    ws.send(JSON.stringify({{ 
                        type: "typing", 
                        toCode: currentTargetCode, 
                        isTyping: false 
                    }}));
                }}, 1000);
            }}
        }};

        function addMessageToChat(targetCode, content, isSent, isFile = false) {{
            if (!chats[targetCode]) chats[targetCode] = [];
            chats[targetCode].push({{ content, isSent, isFile }});
            if (currentTargetCode === targetCode) {{
                renderChat();
            }}
        }}

        function renderChat() {{
            chatsDiv.innerHTML = "";
            const msgs = chats[currentTargetCode] || [];
            msgs.forEach(msg => {{
                const msgDiv = document.createElement("div");
                msgDiv.className = `message ${{msg.isSent ? 'sent' : 'received'}}`;
                if (msg.isFile) {{
                    msgDiv.innerHTML = `<a href="${{msg.content}}" target="_blank" class="file-msg">📁 ملف</a>`;
                } else {{
                    msgDiv.innerText = msg.content;
                }}
                chatsDiv.appendChild(msgDiv);
            }});
            scrollToBottom();
        }}

        function scrollToBottom() {{
            chatsDiv.scrollTop = chatsDiv.scrollHeight;
        }}

        function enableChat(code) {{
            currentTargetCode = code;
            messageInput.disabled = false;
            sendBtn.disabled = false;
            renderChat();
        }}

        function sendMessage(text, isFile = false) {{
            if (!currentTargetCode) return;
            ws.send(JSON.stringify({{ 
                toCode: currentTargetCode, 
                text, 
                isFile 
            }}));
            addMessageToChat(currentTargetCode, text, true, isFile);
            messageInput.value = "";
        }}

        sendBtn.onclick = () => {{
            const text = messageInput.value.trim();
            if (text) sendMessage(text);
        }};

        messageInput.onkeypress = (e) => {{
            if (e.key === "Enter") {{
                e.preventDefault();
                sendBtn.click();
            }}
        }};

        fileBtn.onclick = () => {{
            fileInput.click();
        }};

        fileInput.onchange = async (e) => {{
            const file = e.target.files[0];
            if (file && currentTargetCode) {{
                const formData = new FormData();
                formData.append("file", file);
                formData.append("upload_preset", "''' + CLOUDINARY_UPLOAD_PRESET + '''");
                try {{
                    const res = await fetch("https://api.cloudinary.com/v1_1/''' + CLOUDINARY_CLOUD_NAME + '''/upload", {{
                        method: "POST",
                        body: formData
                    }});
                    const data = await res.json();
                    if (data.secure_url) {{
                        sendMessage(data.secure_url, true);
                    }}
                } catch (err) {{
                    alert("فشل رفع الملف");
                }}
            }}
        }};

        manualCodeInput.oninput = () => {{
            const code = manualCodeInput.value.trim().toUpperCase();
            if (code && !currentTargetCode) {{
                enableChat(code);
            }}
        }};
    </script>
</body>
</html>
'''.strip()

# --- معالج HTTP ---
async def http_handler(path, request_headers):
    from websockets import http
    if path == "/":
        return http.HTTPResponse(
            status_code=200,
            headers=[("Content-Type", "text/html; charset=utf-8")],
            body=HTML.encode("utf-8"),
        )
    elif path == "/manifest.json":
        manifest = '''
        {
            "name": "وَصِل - دردشة فورية",
            "short_name": "وَصِل",
            "description": "دردشة برقم فريد — بدون رقم هاتف",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#075e54",
            "theme_color": "#075e54",
            "icons": [{
                "src": "/icon-192.png",
                "sizes": "192x192",
                "type": "image/png"
            }, {
                "src": "/icon-512.png",
                "sizes": "512x512",
                "type": "image/png"
            }]
        }
        '''
        return http.HTTPResponse(
            status_code=200,
            headers=[("Content-Type", "application/manifest+json")],
            body=manifest.encode("utf-8"),
        )
    elif path == "/sw.js":
        sw = '''
        self.addEventListener('install', (e) => {
            e.waitUntil(caches.open('wasil-v1').then(cache => {
                return cache.addAll(['/']);
            }));
        });
        self.addEventListener('fetch', (e) => {
            e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
        });
        '''
        return http.HTTPResponse(
            status_code=200,
            headers=[("Content-Type", "application/javascript")],
            body=sw.encode("utf-8"),
        )
    elif path in ["/icon-192.png", "/icon-512.png"]:
        # إرجاع أيقونة افتراضية (SVG كـ PNG بديل)
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y=".9em" font-size="90">💬</text></svg>'
        return http.HTTPResponse(
            status_code=200,
            headers=[("Content-Type", "image/svg+xml")],
            body=svg.encode("utf-8"),
        )
    return http.HTTPResponse(status_code=404)

# --- معالج WebSocket مع دعم المؤشر ---
async def ws_handler(websocket, path):
    if path != "/ws":
        await websocket.close(1002, "Invalid path")
        return

    my_code = None
    try:
        init = await websocket.recv()
        data = json.loads(init)
        provided_code = data.get("myCode")
        my_name = str(data.get("myName", "مجهول"))[:20]
        my_avatar = data.get("myAvatar")

        if not provided_code or len(provided_code) != 5 or not provided_code.isalnum():
            my_code = generate_code()
            while my_code in online_users:
                my_code = generate_code()
        else:
            my_code = provided_code

        online_users[my_code] = {
            "ws": websocket,
            "name": my_name,
            "avatar": my_avatar
        }
        print(f"✅ دخل: {my_name} ({my_code})")

        await websocket.send(json.dumps({
            "type": "init",
            "myCode": my_code
        }))

        async for msg in websocket:
            data = json.loads(msg)
            msg_type = data.get("type")

            if msg_type == "typing":
                to_code = data.get("toCode")
                is_typing = data.get("isTyping", False)
                if to_code in online_users:
                    await online_users[to_code]["ws"].send(json.dumps({
                        "type": "typing",
                        "fromCode": my_code,
                        "isTyping": is_typing
                    }))

            elif "toCode" in data:
                to_code = data["toCode"]
                text = data.get("text", "")
                is_file = data.get("isFile", False)
                if to_code in online_users and text:
                    await online_users[to_code]["ws"].send(json.dumps({
                        "type": "message",
                        "fromCode": my_code,
                        "content": text,
                        "isFile": is_file
                    }))
    except:
        pass
    finally:
        if my_code in online_users:
            del online_users[my_code]
            print(f"🔚 خرج: {my_name} ({my_code})")

# --- التشغيل ---
if __name__ == "__main__":
    print(f"🚀 جاهز على المنفذ {PORT}")
    server = websockets.serve(
        ws_handler,
        HOST,
        PORT,
        process_request=http_handler,
    )
    asyncio.run(server)
