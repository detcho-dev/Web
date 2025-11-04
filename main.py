# mobile_chat.py
import asyncio
import websockets
import json
import os
from functools import partial
from datetime import datetime

PORT = int(os.environ.get("PORT", 8000))
HOST = "0.0.0.0"

# تخزين المستخدمين المتصلين: { user_id: websocket }
online_users = {}

# --- واجهة HTML محسّنة للهواتف ---
HTML = '''
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>دردشتي</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', Tahoma, sans-serif; }
        body {
            background: #e5ddd5;
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        .header {
            background: #075e54;
            color: white;
            padding: 12px 15px;
            text-align: center;
            font-weight: bold;
            font-size: 18px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.2);
            position: relative;
        }
        #myId {
            background: rgba(255,255,255,0.2);
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 14px;
            margin-top: 4px;
        }
        .chat-area {
            flex: 1;
            display: flex;
            flex-direction: column;
            padding: 10px;
        }
        #messages {
            flex: 1;
            background: white;
            padding: 15px;
            border-radius: 12px;
            overflow-y: auto;
            margin-bottom: 15px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .message {
            max-width: 70%;
            padding: 8px 12px;
            margin-bottom: 8px;
            border-radius: 12px;
            word-wrap: break-word;
            line-height: 1.4;
            position: relative;
        }
        .received {
            background: #ffffff;
            border: 1px solid #e0e0e0;
            align-self: flex-start;
            border-top-left-radius: 3px;
        }
        .sent {
            background: #dcf8c6;
            margin-left: auto;
            border-top-right-radius: 3px;
        }
        .input-area {
            display: flex;
            gap: 8px;
        }
        #targetInput, #messageInput {
            padding: 12px;
            border: 1px solid #ccc;
            border-radius: 24px;
            font-size: 16px; /* يمنع التكبير التلقائي في iOS */
            outline: none;
        }
        #targetInput { flex: 0 0 100px; text-align: center; }
        #messageInput { flex: 1; }
        #sendBtn {
            background: #075e54;
            color: white;
            border: none;
            width: 44px;
            height: 44px;
            border-radius: 50%;
            font-size: 18px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
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
    </style>
</head>
<body>
    <div class="header">
        دردشتي 📱
        <div id="myId">يتم التحميل...</div>
    </div>

    <div class="chat-area">
        <div id="messages">
            <div class="placeholder">ابدأ محادثة بإدخال رقم صديقك!</div>
        </div>
        <div class="input-area">
            <input type="text" id="targetInput" placeholder="رقم" maxlength="10">
            <input type="text" id="messageInput" placeholder="اكتب رسالتك..." autocomplete="off">
            <button id="sendBtn">➤</button>
        </div>
    </div>

    <script>
        // --- 1. إدارة الهوية ---
        let myId = localStorage.getItem("userId");
        if (!myId || !/^\d{4,10}$/.test(myId)) {
            myId = Math.floor(10000 + Math.random() * 900000).toString();
            localStorage.setItem("userId", myId);
        }
        document.getElementById("myId").innerText = myId;

        // --- 2. الاتصال بالخادم ---
        const ws = new WebSocket("wss://" + window.location.host + "/ws");
        const messagesDiv = document.getElementById("messages");
        const targetInput = document.getElementById("targetInput");
        const messageInput = document.getElementById("messageInput");

        ws.onopen = () => {
            ws.send(JSON.stringify({ userId: myId }));
        };

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === "message") {
                addMessage(data.text, data.from === myId, data.time);
            }
        };

        // --- 3. وظائف المساعدة ---
        function addMessage(text, isSent, time) {
            // إزالة رسالة الترحيب إذا كانت موجودة
            if (messagesDiv.querySelector(".placeholder")) {
                messagesDiv.innerHTML = "";
            }

            const msgDiv = document.createElement("div");
            msgDiv.className = `message ${isSent ? 'sent' : 'received'}`;
            msgDiv.innerHTML = `${text}<div class="time">${time}</div>`;
            messagesDiv.appendChild(msgDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }

        function sendMessage() {
            const to = targetInput.value.trim();
            const text = messageInput.value.trim();
            const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

            if (to && text && to !== myId && /^\d{4,10}$/.test(to)) {
                ws.send(JSON.stringify({ to, text }));
                addMessage(text, true, now);
                messageInput.value = "";
                messageInput.focus();
            } else if (!to) {
                alert("⚠️ أدخل رقم صديقك أولاً!");
            }
        }

        // --- 4. أحداث ---
        document.getElementById("sendBtn").onclick = sendMessage;
        messageInput.onkeypress = (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                sendMessage();
            }
        };

        // منع التكبير عند الضغط على الإدخال (خاصة iOS)
        document.querySelectorAll("input").forEach(input => {
            input.addEventListener("focus", () => {
                document.body.scrollTop = 0;
            });
        });
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

    user_id = None
    try:
        init = await websocket.recv()
        data = json.loads(init)
        user_id = str(data.get("userId", "")).strip()
        if not (user_id.isdigit() and 4 <= len(user_id) <= 10):
            await websocket.close(1003, "Invalid ID")
            return
        if user_id in online_users:
            await websocket.close(1008, "Already connected")
            return

        online_users[user_id] = websocket
        print(f"📱 دخل: {user_id}")

        async for msg in websocket:
            try:
                data = json.loads(msg)
                to = data.get("to")
                text = data.get("text", "").strip()
                if to in online_users and text:
                    await online_users[to].send(json.dumps({
                        "type": "message",
                        "from": user_id,
                        "text": text,
                        "time": datetime.now().strftime("%H:%M")
                    }))
            except:
                pass
    except:
        pass
    finally:
        if user_id in online_users:
            del online_users[user_id]
            print(f"🔚 خرج: {user_id}")

# --- التشغيل ---
if __name__ == "__main__":
    print(f"🚀 جاهز للعمل على المنفذ {PORT}")
    server = websockets.serve(
        ws_handler,
        HOST,
        PORT,
        process_request=http_handler,
    )
    asyncio.run(server)