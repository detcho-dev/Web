# smart_chat.py
import asyncio
import websockets
import json
import os
import secrets
from functools import partial
from datetime import datetime

PORT = int(os.environ.get("PORT", 8000))
HOST = "0.0.0.0"

# { code: { "ws": websocket, "name": "اسم" } }
online_users = {}

def generate_code():
    """يولّد كود فريد من 5 أحرف/أرقام (مثل: A3K9M)"""
    return secrets.token_urlsafe(4).replace("_", "").replace("-", "").upper()[:5]

# --- واجهة HTML نهائية ---
HTML = '''
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>دردشتي</title>
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
        }
        .chat-area {
            flex: 1;
            display: flex;
            flex-direction: column;
            padding: 10px;
        }
        #messages {
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
            background: var(--msg-bg);
            margin-left: auto;
        }
        .received {
            background: var(--border);
            margin-left: 0;
        }
        .input-area {
            display: flex;
            gap: 8px;
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
        #manualCode { flex: 0 0 120px; text-align: center; }
        #messageInput { flex: 1; }
        #sendBtn {
            background: var(--header);
            color: white;
            border: none;
            width: 46px;
            height: 46px;
            border-radius: 50%;
            font-size: 18px;
            cursor: pointer;
        }
        .placeholder {
            color: #999;
            text-align: center;
            padding: 20px;
        }
        .time {
            font-size: 10px;
            color: #999;
            text-align: right;
            margin-top: 4px;
        }
        .info {
            text-align: center;
            padding: 8px;
            font-size: 14px;
            color: #666;
        }
        #yourLink {
            display: block;
            margin: 8px auto;
            padding: 8px;
            background: rgba(0,0,0,0.05);
            border-radius: 6px;
            font-size: 13px;
            color: var(--header);
            text-decoration: none;
            max-width: 90%;
            overflow: hidden;
            text-overflow: ellipsis;
        }
    </style>
</head>
<body>
    <div class="header">دردشتي 🌐</div>
    <div class="chat-area">
        <div id="messages">
            <div class="placeholder">جاري الاتصال...</div>
        </div>
        <div class="info">
            <a id="yourLink" href="#" target="_blank">يتم التحميل...</a>
        </div>
        <div class="input-area">
            <input type="text" id="manualCode" placeholder="كود" maxlength="10">
            <input type="text" id="messageInput" placeholder="اكتب رسالتك..." autocomplete="off" disabled>
            <button id="sendBtn" disabled>➤</button>
        </div>
    </div>

    <script>
        // --- 1. اقرأ الكود من الرابط (إذا وُجد) ---
        const urlParams = new URLSearchParams(window.location.search);
        const targetCode = urlParams.get('c'); // c = code

        // --- 2. احصل على الهوية ---
        let myCode = localStorage.getItem("myCode");
        let myName = localStorage.getItem("myName") || "";

        if (!myCode) {
            // سنطلب الاسم أول مرة فقط
            const name = prompt("مرحباً! ما اسمك؟", "ضيف");
            if (name && name.trim()) {
                myName = name.trim().substring(0, 20);
                localStorage.setItem("myName", myName);
            }
        }

        // --- 3. الاتصال بالخادم ---
        const ws = new WebSocket("wss://" + window.location.host + "/ws");
        const messagesDiv = document.getElementById("messages");
        const messageInput = document.getElementById("messageInput");
        const sendBtn = document.getElementById("sendBtn");
        const manualCodeInput = document.getElementById("manualCode");
        const yourLink = document.getElementById("yourLink");

        let currentTargetCode = targetCode; // إذا فتح برابط، نستخدمه تلقائيًا

        ws.onopen = () => {
            ws.send(JSON.stringify({
                myCode: myCode,
                myName: myName
            }));
        };

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            
            if (data.type === "init") {
                // الخادم أرسل كودك الجديد
                myCode = data.myCode;
                localStorage.setItem("myCode", myCode);
                const fullLink = `${window.location.origin}?c=${myCode}`;
                yourLink.href = fullLink;
                yourLink.innerText = "شارك رابط دردشتك:";
                yourLink.title = fullLink;

                // إذا كان هناك كود مستهدف (من الرابط)، ابدأ الدردشة
                if (targetCode) {
                    currentTargetCode = targetCode;
                    messageInput.disabled = false;
                    sendBtn.disabled = false;
                    messagesDiv.innerHTML = `<div class="placeholder">جاهز للدردشة مع: ${targetCode}</div>`;
                }
            }

            if (data.type === "message") {
                if (messagesDiv.querySelector(".placeholder")) {
                    messagesDiv.innerHTML = "";
                }
                const msgDiv = document.createElement("div");
                msgDiv.className = "message received";
                msgDiv.innerHTML = `${data.text}<div class="time">${data.time}</div>`;
                messagesDiv.appendChild(msgDiv);
                messagesDiv.scrollTop = messagesDiv.scrollHeight;
            }
        };

        // --- 4. إرسال الرسالة ---
        function sendMessage() {
            const text = messageInput.value.trim();
            const code = currentTargetCode || manualCodeInput.value.trim().toUpperCase();
            if (text && code) {
                ws.send(JSON.stringify({ toCode: code, text }));
                const msgDiv = document.createElement("div");
                msgDiv.className = "message";
                msgDiv.innerHTML = `${text}<div class="time">${new Date().toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}</div>`;
                messagesDiv.appendChild(msgDiv);
                messagesDiv.scrollTop = messagesDiv.scrollHeight;
                messageInput.value = "";
                if (!currentTargetCode) {
                    manualCodeInput.value = "";
                }
            }
        }

        sendBtn.onclick = sendMessage;
        messageInput.onkeypress = (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                sendMessage();
            }
        };

        // تمكين الإرسال عند إدخال كود يدوي
        manualCodeInput.oninput = () => {
            if (manualCodeInput.value.trim() && !currentTargetCode) {
                messageInput.disabled = false;
                sendBtn.disabled = false;
            }
        };
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
    return http.HTTPResponse(status_code=404)

# --- معالج WebSocket ---
async def ws_handler(websocket, path):
    if path != "/ws":
        await websocket.close(1002, "Invalid path")
        return

    my_code = None
    my_name = "مجهول"
    try:
        init = await websocket.recv()
        data = json.loads(init)
        provided_code = data.get("myCode")
        my_name = str(data.get("myName", "مجهول"))[:20]

        # إذا لم يُرسل كود (أو غير صالح)، نولّد واحدًا جديدًا
        if not provided_code or len(provided_code) != 5 or not provided_code.isalnum():
            my_code = generate_code()
            # تأكد من التفرد
            while my_code in online_users:
                my_code = generate_code()
        else:
            my_code = provided_code

        online_users[my_code] = {
            "ws": websocket,
            "name": my_name
        }
        print(f"✅ دخل: {my_name} ({my_code})")

        # أرسل الكود للمستخدم
        await websocket.send(json.dumps({
            "type": "init",
            "myCode": my_code
        }))

        async for msg in websocket:
            try:
                data = json.loads(msg)
                to_code = data.get("toCode", "").strip().upper()
                text = data.get("text", "").strip()
                if to_code in online_users and text:
                    await online_users[to_code]["ws"].send(json.dumps({
                        "type": "message",
                        "text": f"{my_name}: {text}",
                        "time": datetime.now().strftime("%H:%M")
                    }))
            except:
                pass
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
