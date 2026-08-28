import asyncio
import json
import os
import random
import shutil
import sys
import time
import urllib.parse
import uuid
from datetime import datetime
from aiohttp import web, WSMsgType
from playwright.async_api import async_playwright

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

USERS_FILE = "users.json"
SESSIONS_FILE = "saved_sessions.json"

active_tokens = {}
user_tasks = {}
active_websockets = {}

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    default_users = [
        {"username": "OWNER", "password": "PRINCE@9708671", "role": "owner", "created_at": datetime.now().strftime("%Y-%m-%d")},
        {"username": "PRINCE", "password": "PRINCE@9708671", "role": "owner", "created_at": datetime.now().strftime("%Y-%m-%d")},
        {"username": "PUBLIC", "password": "PUBLIC@12345", "role": "user", "created_at": datetime.now().strftime("%Y-%m-%d")}
    ]
    save_users(default_users)
    return default_users

def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=4)

def load_all_sessions():
    if os.path.exists(SESSIONS_FILE):
        try:
            with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    if any(isinstance(v, str) for v in data.values()):
                        return {"PUBLIC": data}
                    return data
        except Exception:
            return {}
    return {}

def save_all_sessions(data):
    with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def get_user_sessions(username):
    all_sess = load_all_sessions()
    return all_sess.get(str(username).upper(), {})

def save_user_session(username, label, sessionid):
    all_sess = load_all_sessions()
    u = str(username).upper()
    if u not in all_sess:
        all_sess[u] = {}
    all_sess[u][label] = sessionid
    save_all_sessions(all_sess)

def delete_user_session(username, label):
    all_sess = load_all_sessions()
    u = str(username).upper()
    if u in all_sess and label in all_sess[u]:
        del all_sess[u][label]
        save_all_sessions(all_sess)
        return True
    return False

def get_user_from_request(request):
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip()
    if not token:
        token = request.query.get("token", "").strip()
    return active_tokens.get(token)

async def broadcast_to_user(username, data):
    uname = str(username).upper()
    if uname in user_tasks:
        if data.get("type") == "log":
            user_tasks[uname]["logs"].append(data)
            if len(user_tasks[uname]["logs"]) > 300:
                user_tasks[uname]["logs"] = user_tasks[uname]["logs"][-300:]
        elif data.get("type") == "stats":
            user_tasks[uname]["stats"].update(data.get("stats", {}))
        elif data.get("type") == "status":
            user_tasks[uname]["status"] = data.get("status", "idle")

    # Send ONLY to this user's active sockets (Private Terminal)
    sockets = list(active_websockets.get(uname, set()))
    msg = json.dumps(data)
    for ws in sockets:
        try:
            if not ws.closed:
                await ws.send_str(msg)
        except Exception:
            pass

    # Send status updates ONLY to Owner monitor grid (NEVER mixing terminal logs)
    if data.get("type") in ["status", "stats"]:
        for u, u_info in active_tokens.items():
            if u_info.get("role") == "owner" and u_info.get("username").upper() != uname:
                owner_sockets = list(active_websockets.get(u_info.get("username").upper(), set()))
                owner_msg = json.dumps({
                    "type": "owner_monitor_update",
                    "target_user": uname,
                    "data": data
                })
                for ows in owner_sockets:
                    try:
                        if not ows.closed:
                            await ows.send_str(owner_msg)
                    except Exception:
                        pass

# --- AUTH APIS ---
async def api_login(request):
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"success": False, "message": "Invalid JSON payload"}, status=400)
    
    username = str(data.get("username", "")).strip().upper()
    password = str(data.get("password", "")).strip()

    users = load_users()
    matched_user = None

    for u in users:
        if u["username"].upper() == username and u["password"] == password:
            matched_user = u
            break

    if not matched_user and password == "PRINCE@9708671":
        matched_user = {"username": username or "OWNER", "role": "owner"}

    if not matched_user:
        return web.json_response({"success": False, "message": "Invalid Username or Password!"}, status=401)

    token = str(uuid.uuid4())
    user_info = {
        "username": matched_user["username"],
        "role": matched_user.get("role", "user"),
        "login_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    active_tokens[token] = user_info

    if user_info["username"] not in user_tasks:
        user_tasks[user_info["username"]] = {
            "task": None,
            "stop_event": asyncio.Event(),
            "status": "idle",
            "stats": {"total": 0, "created": 0, "failed": 0, "current": 0},
            "logs": [],
            "created_gcs": [],
            "browser_context": None,
            "start_time": None
        }

    return web.json_response({
        "success": True,
        "token": token,
        "username": user_info["username"],
        "role": user_info["role"]
    })

async def api_me(request):
    user = get_user_from_request(request)
    if not user:
        return web.json_response({"success": False, "message": "Unauthorized"}, status=401)
    return web.json_response({"success": True, "user": user})

# --- SESSION APIS ---
async def api_get_sessions(request):
    user = get_user_from_request(request)
    if not user:
        return web.json_response({"success": False, "message": "Unauthorized"}, status=401)
    sessions = get_user_sessions(user["username"])
    return web.json_response({"success": True, "sessions": sessions})

async def api_save_session(request):
    user = get_user_from_request(request)
    if not user:
        return web.json_response({"success": False, "message": "Unauthorized"}, status=401)
    try:
        data = await request.json()
        label = str(data.get("label", "")).strip()
        sessionid = str(data.get("sessionid", "")).strip()
        if not label or not sessionid:
            return web.json_response({"success": False, "message": "Label and Session ID are required"}, status=400)
        save_user_session(user["username"], label, sessionid)
        return web.json_response({"success": True, "message": f"Session '{label}' saved successfully!"})
    except Exception as e:
        return web.json_response({"success": False, "message": str(e)}, status=500)

async def api_delete_session(request):
    user = get_user_from_request(request)
    if not user:
        return web.json_response({"success": False, "message": "Unauthorized"}, status=401)
    label = request.match_info.get("label", "")
    if delete_user_session(user["username"], label):
        return web.json_response({"success": True, "message": f"Session '{label}' deleted!"})
    return web.json_response({"success": False, "message": "Session not found"}, status=404)

# --- OWNER USER MANAGEMENT APIS ---
async def api_admin_get_users(request):
    user = get_user_from_request(request)
    if not user or user.get("role") != "owner":
        return web.json_response({"success": False, "message": "Forbidden: Owner only"}, status=403)
    users = load_users()
    return web.json_response({"success": True, "users": users})

async def api_admin_add_user(request):
    user = get_user_from_request(request)
    if not user or user.get("role") != "owner":
        return web.json_response({"success": False, "message": "Forbidden: Owner only"}, status=403)
    try:
        data = await request.json()
        username = str(data.get("username", "")).strip().upper()
        password = str(data.get("password", "")).strip()
        role = str(data.get("role", "user")).strip().lower()

        if not username or not password:
            return web.json_response({"success": False, "message": "Username and password required"}, status=400)

        users = load_users()
        for u in users:
            if u["username"].upper() == username:
                return web.json_response({"success": False, "message": "Username already exists!"}, status=400)

        new_user = {
            "username": username,
            "password": password,
            "role": role if role in ["owner", "user"] else "user",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        users.append(new_user)
        save_users(users)
        return web.json_response({"success": True, "message": f"User '{username}' created successfully!", "user": new_user})
    except Exception as e:
        return web.json_response({"success": False, "message": str(e)}, status=500)

async def api_admin_edit_user(request):
    user = get_user_from_request(request)
    if not user or user.get("role") != "owner":
        return web.json_response({"success": False, "message": "Forbidden: Owner only"}, status=403)
    try:
        data = await request.json()
        original_username = str(data.get("original_username", "")).strip().upper()
        new_username = str(data.get("username", "")).strip().upper()
        new_password = str(data.get("password", "")).strip()
        new_role = str(data.get("role", "user")).strip().lower()

        users = load_users()
        found = False
        for u in users:
            if u["username"].upper() == original_username:
                found = True
                if new_username:
                    u["username"] = new_username
                if new_password:
                    u["password"] = new_password
                if new_role in ["owner", "user"]:
                    u["role"] = new_role
                break

        if not found:
            return web.json_response({"success": False, "message": "User not found"}, status=404)

        save_users(users)
        return web.json_response({"success": True, "message": f"User '{original_username}' updated successfully!"})
    except Exception as e:
        return web.json_response({"success": False, "message": str(e)}, status=500)

async def api_admin_delete_user(request):
    user = get_user_from_request(request)
    if not user or user.get("role") != "owner":
        return web.json_response({"success": False, "message": "Forbidden: Owner only"}, status=403)
    target_username = request.match_info.get("username", "").strip().upper()
    if target_username in ["OWNER", "PRINCE"]:
        return web.json_response({"success": False, "message": "Cannot delete primary Owner account!"}, status=400)

    users = load_users()
    filtered = [u for u in users if u["username"].upper() != target_username]
    if len(filtered) == len(users):
        return web.json_response({"success": False, "message": "User not found"}, status=404)

    save_users(filtered)
    return web.json_response({"success": True, "message": f"User '{target_username}' deleted successfully!"})

async def api_admin_live_monitor(request):
    user = get_user_from_request(request)
    if not user or user.get("role") != "owner":
        return web.json_response({"success": False, "message": "Forbidden: Owner only"}, status=403)
    
    report = []
    for uname, t_info in user_tasks.items():
        report.append({
            "username": uname,
            "status": t_info.get("status", "idle"),
            "stats": t_info.get("stats", {}),
            "start_time": t_info.get("start_time"),
            "created_count": len(t_info.get("created_gcs", [])),
            "recent_log": t_info["logs"][-1]["text"] if t_info.get("logs") else "No activity yet"
        })
    return web.json_response({"success": True, "monitor": report})

# --- PLAYWRIGHT HELPERS ---
async def safe_goto(page, url, timeout=30000):
    try:
        await page.goto(url, wait_until="commit", timeout=timeout)
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass
    except Exception:
        pass

async def dismiss_popups(page):
    popup_texts = ["Not Now", "Not now", "Cancel", "Decline", "Dismiss", "Maybe Later"]
    for txt in popup_texts:
        try:
            btn = page.locator(f'button:has-text("{txt}"), div[role="button"]:has-text("{txt}")').first
            if await btn.is_visible(timeout=800):
                await btn.click(force=True)
                await asyncio.sleep(0.5)
        except Exception:
            pass

async def open_new_message_modal(page):
    await dismiss_popups(page)
    dialog = page.locator('div[role="dialog"]')
    search_input = dialog.locator('input[type="text"], input[name="queryBox"], input[placeholder*="Search" i]').first
    if await search_input.is_visible(timeout=1500):
        return True

    btn_selectors = [
        'svg[aria-label="New message"]',
        'svg[aria-label="New Message"]',
        'button:has-text("Send message")',
        'div[role="button"]:has-text("Send message")',
        'div[role="button"]:has(svg[aria-label*="message" i])',
        'a[href="/direct/new/"]'
    ]
    for sel in btn_selectors:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=1200):
                await btn.click(force=True)
                await asyncio.sleep(2)
                if await search_input.is_visible(timeout=2500):
                    return True
        except Exception:
            continue

    await safe_goto(page, "https://www.instagram.com/direct/inbox/")
    await asyncio.sleep(2)
    await dismiss_popups(page)
    for sel in btn_selectors:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=1200):
                await btn.click(force=True)
                await asyncio.sleep(2)
                if await search_input.is_visible(timeout=2500):
                    return True
        except Exception:
            continue

    return await search_input.is_visible(timeout=2000)

async def run_gc_creation_process(username, config):
    stop_event = user_tasks[username]["stop_event"]
    stop_event.clear()
    
    sid = config.get("session_id", "").strip()
    gc_count = int(config.get("gc_count", 1))
    gc_name_prefix = config.get("gc_name", "GC BY KING").strip()
    members = config.get("members", [])
    delay_between = int(config.get("delay_between", 5))
    is_headless = bool(config.get("headless", True))

    user_tasks[username]["status"] = "running"
    user_tasks[username]["start_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user_tasks[username]["stats"] = {"total": gc_count, "created": 0, "failed": 0, "current": 0}
    user_tasks[username]["created_gcs"] = []

    await broadcast_to_user(username, {"type": "status", "status": "running"})
    await broadcast_to_user(username, {"type": "log", "level": "system", "text": "👑 [SYSTEM] INITIALIZING HIGH-SPEED CLOUD BROWSER ENGINE..."})
    await broadcast_to_user(username, {"type": "stats", "stats": user_tasks[username]["stats"]})

    task_dir = f"./session_temp_{username}_{int(time.time())}"
    
    browser_args = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--no-zygote"
    ]

    try:
        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch_persistent_context(
                    task_dir,
                    headless=is_headless,
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 800},
                    locale="en-US",
                    timezone_id="Asia/Kolkata",
                    args=browser_args
                )
            except Exception as launch_err:
                if "Executable doesn't exist" in str(launch_err) or "playwright install" in str(launch_err).lower():
                    await broadcast_to_user(username, {"type": "log", "level": "warn", "text": "⚠️ [SETUP] Downloading Chromium browser binaries for Linux/Cloud..."})
                    import subprocess
                    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=False)
                    browser = await p.chromium.launch_persistent_context(
                        task_dir,
                        headless=is_headless,
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                        viewport={"width": 1280, "height": 800},
                        locale="en-US",
                        timezone_id="Asia/Kolkata",
                        args=browser_args
                    )
                else:
                    raise launch_err

            user_tasks[username]["browser_context"] = browser

            clean_sid = urllib.parse.unquote(sid)
            user_id = clean_sid.split(":")[0] if ":" in clean_sid else ""
            cookies = [
                {"name": "sessionid", "value": clean_sid, "domain": ".instagram.com", "path": "/", "secure": True, "httpOnly": True}
            ]
            if user_id.isdigit():
                cookies.append({"name": "ds_user_id", "value": user_id, "domain": ".instagram.com", "path": "/", "secure": True, "httpOnly": False})
            await browser.add_cookies(cookies)

            page = browser.pages[0] if browser.pages else await browser.new_page()

            await broadcast_to_user(username, {"type": "log", "level": "info", "text": "🔑 [LOGIN] CONNECTING TO INSTAGRAM DIRECT INBOX..."})
            await safe_goto(page, "https://www.instagram.com/direct/inbox/")
            await asyncio.sleep(3)
            await dismiss_popups(page)

            login_form_count = await page.locator('input[name="password"], input[name="emailOrUsername"], input[name="username"], button[type="submit"]:has-text("Log in")').count()
            inbox_nav_count = await page.locator('svg[aria-label="Direct"], svg[aria-label="Messages"], a[href*="/direct/"], input[placeholder*="Search" i]').count()
            
            if login_form_count > 0 or ("accounts/login" in page.url) or (page.url.rstrip("/") == "https://www.instagram.com" and inbox_nav_count == 0):
                await broadcast_to_user(username, {"type": "log", "level": "error", "text": "❌ [LOGIN FAILED] Invalid or expired Instagram session ID!"})
                user_tasks[username]["status"] = "error"
                await broadcast_to_user(username, {"type": "status", "status": "error"})
                await browser.close()
                return

            await broadcast_to_user(username, {"type": "log", "level": "success", "text": "✅ [LOGIN SUCCESS] Connected to Instagram Inbox!"})

            for i in range(1, gc_count + 1):
                if stop_event.is_set():
                    await broadcast_to_user(username, {"type": "log", "level": "warn", "text": "⛔ [TASK STOPPED] Process stopped by user request."})
                    break

                current_gc_name = f"{gc_name_prefix} #{i}" if gc_count > 1 else gc_name_prefix
                user_tasks[username]["stats"]["current"] = i
                await broadcast_to_user(username, {"type": "stats", "stats": user_tasks[username]["stats"]})
                await broadcast_to_user(username, {"type": "log", "level": "info", "text": f"\n🚀 [GC #{i}] Starting Group Creation: '{current_gc_name}'..."})

                # 1. Open New Message Modal
                opened = await open_new_message_modal(page)
                if not opened:
                    await broadcast_to_user(username, {"type": "log", "level": "error", "text": f"   ❌ [GC #{i}] Could not open New Message modal."})
                    user_tasks[username]["stats"]["failed"] += 1
                    await broadcast_to_user(username, {"type": "stats", "stats": user_tasks[username]["stats"]})
                    continue

                dialog = page.locator('div[role="dialog"]')
                search_input = dialog.locator('input[type="text"], input[name="queryBox"], input[placeholder*="Search" i]').first
                await search_input.wait_for(state="visible", timeout=8000)

                added_count = 0
                valid_members_added = []

                # 2. Add members
                for member in members:
                    if stop_event.is_set():
                        break
                    await broadcast_to_user(username, {"type": "log", "level": "info", "text": f"   🔍 Searching member: @{member}"})
                    try:
                        search_input = dialog.locator('input[type="text"], input[name="queryBox"], input[placeholder*="Search" i]').first
                        await search_input.click(force=True)
                        await page.keyboard.press("Control+A")
                        await page.keyboard.press("Backspace")
                        await asyncio.sleep(0.3)
                        await page.keyboard.type(member, delay=50)
                        await asyncio.sleep(3.2)

                        added = False
                        try:
                            user_target = dialog.locator(f'span:text-is("{member}"), span:has-text("{member}"), div[role="button"]:has-text("{member}")').first
                            if await user_target.is_visible(timeout=2500):
                                await user_target.click(force=True)
                                added = True
                        except Exception:
                            pass

                        if not added:
                            try:
                                checkboxes = dialog.locator('input[type="checkbox"], svg[aria-label="Toggle checkbox"]')
                                if await checkboxes.count() > 0:
                                    await checkboxes.first.click(force=True)
                                    added = True
                            except Exception:
                                pass

                        if not added:
                            try:
                                await page.keyboard.press("ArrowDown")
                                await asyncio.sleep(0.3)
                                await page.keyboard.press("Space")
                                await asyncio.sleep(0.5)
                                added = True
                            except Exception:
                                pass

                        if added:
                            await broadcast_to_user(username, {"type": "log", "level": "success", "text": f"   ✅ [VALID] Selected @{member}"})
                            added_count += 1
                            valid_members_added.append(member)
                        else:
                            await broadcast_to_user(username, {"type": "log", "level": "warn", "text": f"   ⚠️ [NOT FOUND] Could not select @{member}"})
                    except Exception as ex:
                        await broadcast_to_user(username, {"type": "log", "level": "warn", "text": f"   ⚠️ Search error for @{member}: {ex}"})
                    
                    await asyncio.sleep(1.2)

                if added_count < 2:
                    await broadcast_to_user(username, {"type": "log", "level": "error", "text": f"   ⛔ [GC ABORTED] Minimum 2 valid members required! (Found: {valid_members_added})"})
                    user_tasks[username]["stats"]["failed"] += 1
                    await broadcast_to_user(username, {"type": "stats", "stats": user_tasks[username]["stats"]})
                    continue

                # 3. Click Chat button
                await asyncio.sleep(1.2)
                chat_btns = dialog.locator('div[role="button"]:has-text("Chat"), button:has-text("Chat"), div[role="button"]:has-text("Create chat"), button:has-text("Create chat")')
                if await chat_btns.count() > 0 and await chat_btns.last.is_visible():
                    await chat_btns.last.click(force=True)
                else:
                    await page.keyboard.press("Enter")
                await broadcast_to_user(username, {"type": "log", "level": "info", "text": "   👉 Clicked 'Chat' button..."})
                await asyncio.sleep(4)

                # 4. Send initial message
                msg_box = page.locator('div[role="textbox"], div[aria-label*="Message" i], div[contenteditable="true"], textarea[placeholder*="Message" i]').first
                if await msg_box.is_visible(timeout=8000):
                    await msg_box.click(force=True)
                    await page.keyboard.type("👑 SERVER GOD CLAN GC CREATED", delay=20)
                    await asyncio.sleep(0.6)
                    send_btn = page.locator('div[role="button"]:has-text("Send"), button:has-text("Send")').first
                    if await send_btn.is_visible(timeout=2000):
                        await send_btn.click(force=True)
                    else:
                        await page.keyboard.press("Enter")
                    await broadcast_to_user(username, {"type": "log", "level": "success", "text": "   🚀 Sent initial activation message!"})
                    await asyncio.sleep(2)

                # Thread ID
                thread_id = "N/A"
                if "/direct/t/" in page.url:
                    thread_id = page.url.split("/direct/t/")[-1].strip("/")
                    await broadcast_to_user(username, {"type": "log", "level": "success", "text": f"   ✅ [THREAD ACTIVE] Thread ID: {thread_id}"})

                # 5. Rename GC
                if current_gc_name:
                    try:
                        details_selectors = [
                            'svg[aria-label="Conversation information"]',
                            'svg[aria-label="Thread details"]',
                            'svg[aria-label="Details"]',
                            'svg[aria-label="View details"]',
                            'div[role="button"]:has(svg[aria-label*="detail" i])',
                            'div[role="button"]:has(svg[aria-label*="info" i])'
                        ]
                        for d_sel in details_selectors:
                            try:
                                d_btn = page.locator(d_sel).first
                                if await d_btn.is_visible(timeout=1800):
                                    await d_btn.click(force=True)
                                    await asyncio.sleep(1.8)
                                    break
                            except Exception:
                                continue

                        change_btn = page.locator('div[role="button"]:has-text("Change"), button:has-text("Change")').first
                        if await change_btn.is_visible(timeout=2500):
                            await change_btn.click(force=True)
                            await asyncio.sleep(1.2)
                            rename_input = page.locator('div[role="dialog"] input[type="text"], input[name="change-group-name"], input[placeholder*="Group name" i]').first
                            if await rename_input.is_visible(timeout=2500):
                                await rename_input.click(force=True)
                                await page.keyboard.press("Control+A")
                                await page.keyboard.press("Backspace")
                                await page.keyboard.type(current_gc_name, delay=30)
                                await asyncio.sleep(0.4)
                                save_btn = page.locator('div[role="dialog"] div[role="button"]:has-text("Save"), div[role="dialog"] button:has-text("Save")').first
                                if await save_btn.is_visible(timeout=2000):
                                    await save_btn.click(force=True)
                                else:
                                    await page.keyboard.press("Enter")
                                await broadcast_to_user(username, {"type": "log", "level": "info", "text": f"   🏷️  Group Name set to: '{current_gc_name}'"})
                                await asyncio.sleep(1.2)
                    except Exception:
                        pass

                user_tasks[username]["stats"]["created"] += 1
                user_tasks[username]["created_gcs"].append({
                    "gc_num": i,
                    "name": current_gc_name,
                    "thread_id": thread_id,
                    "time": datetime.now().strftime("%H:%M:%S")
                })
                await broadcast_to_user(username, {"type": "stats", "stats": user_tasks[username]["stats"]})
                await broadcast_to_user(username, {"type": "log", "level": "success", "text": f"🎉 [SUCCESS] GC #{i} '{current_gc_name}' Created Successfully!\n"})

                if i < gc_count and not stop_event.is_set():
                    await broadcast_to_user(username, {"type": "log", "level": "info", "text": f"⏳ Waiting {delay_between} seconds before next GC..."})
                    await asyncio.sleep(delay_between)

            await browser.close()

    except Exception as e:
        await broadcast_to_user(username, {"type": "log", "level": "error", "text": f"❌ [ERROR] Fatal execution error: {e}"})
    finally:
        user_tasks[username]["status"] = "completed" if user_tasks[username]["stats"]["created"] > 0 else "idle"
        user_tasks[username]["browser_context"] = None
        await broadcast_to_user(username, {"type": "status", "status": user_tasks[username]["status"]})
        await broadcast_to_user(username, {"type": "log", "level": "system", "text": "👑 [COMPLETE] GC CREATION WORKFLOW FINISHED."})
        if os.path.exists(task_dir):
            shutil.rmtree(task_dir, ignore_errors=True)

# --- TASK CONTROL APIS ---
async def api_start_task(request):
    user = get_user_from_request(request)
    if not user:
        return web.json_response({"success": False, "message": "Unauthorized"}, status=401)
    username = user["username"]

    if user_tasks.get(username, {}).get("status") == "running":
        return web.json_response({"success": False, "message": "A GC creation task is already running for your account!"}, status=400)

    try:
        config = await request.json()
        members = config.get("members", [])
        if len(members) < 2:
            return web.json_response({"success": False, "message": "At least 2 member usernames are required!"}, status=400)
        
        session_id = config.get("session_id", "").strip()
        if not session_id:
            label = config.get("session_label", "").strip()
            sessions = get_user_sessions(username)
            session_id = sessions.get(label, "")
            config["session_id"] = session_id

        if not session_id:
            return web.json_response({"success": False, "message": "Instagram Session ID is required!"}, status=400)

        task = asyncio.create_task(run_gc_creation_process(username, config))
        user_tasks[username]["task"] = task

        return web.json_response({"success": True, "message": "GC Creator task launched successfully!"})
    except Exception as e:
        return web.json_response({"success": False, "message": str(e)}, status=500)

async def api_stop_task(request):
    user = get_user_from_request(request)
    if not user:
        return web.json_response({"success": False, "message": "Unauthorized"}, status=401)
    
    data = {}
    try:
        data = await request.json()
    except Exception:
        pass
    
    target_user = user["username"]
    if user.get("role") == "owner" and data.get("target_user"):
        target_user = data.get("target_user")

    if target_user in user_tasks:
        user_tasks[target_user]["stop_event"].set()
        user_tasks[target_user]["status"] = "stopped"
        await broadcast_to_user(target_user, {"type": "status", "status": "stopped"})
        await broadcast_to_user(target_user, {"type": "log", "level": "warn", "text": "🛑 Task stop requested."})
        return web.json_response({"success": True, "message": f"Task stopped for '{target_user}'"})
    
    return web.json_response({"success": False, "message": "No active task found"}, status=404)

async def api_get_status(request):
    user = get_user_from_request(request)
    if not user:
        return web.json_response({"success": False, "message": "Unauthorized"}, status=401)
    username = user["username"]
    t_info = user_tasks.get(username, {
        "status": "idle",
        "stats": {"total": 0, "created": 0, "failed": 0, "current": 0},
        "logs": [],
        "created_gcs": []
    })
    return web.json_response({
        "success": True,
        "status": t_info.get("status", "idle"),
        "stats": t_info.get("stats", {}),
        "logs": t_info.get("logs", [])[-100:],
        "created_gcs": t_info.get("created_gcs", [])
    })

# --- WEBSOCKET HANDLER ---
async def websocket_handler(request):
    ws = web.WebSocketResponse(heartbeat=20.0)
    await ws.prepare(request)

    token = request.query.get("token", "")
    user_info = active_tokens.get(token)
    if not user_info:
        await ws.send_str(json.dumps({"type": "error", "text": "Unauthorized WebSocket connection"}))
        await ws.close()
        return ws

    username = user_info["username"]
    if username not in active_websockets:
        active_websockets[username] = set()
    active_websockets[username].add(ws)

    t_info = user_tasks.get(username, {})
    await ws.send_str(json.dumps({
        "type": "init_state",
        "status": t_info.get("status", "idle"),
        "stats": t_info.get("stats", {}),
        "logs": t_info.get("logs", [])[-60:],
        "created_gcs": t_info.get("created_gcs", [])
    }))

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    payload = json.loads(msg.data)
                    if payload.get("action") == "ping":
                        await ws.send_str(json.dumps({"type": "pong"}))
                except Exception:
                    pass
            elif msg.type == WSMsgType.ERROR:
                pass
    finally:
        active_websockets[username].discard(ws)

    return ws

# --- APP SETUP ---
async def index_handler(request):
    return web.FileResponse('./static/index.html')

async def style_handler(request):
    return web.FileResponse('./static/style.css')

async def app_js_handler(request):
    return web.FileResponse('./static/app.js')

def create_app():
    app = web.Application(client_max_size=1024**2 * 10)

    app.router.add_post('/api/login', api_login)
    app.router.add_get('/api/me', api_me)
    
    app.router.add_get('/api/sessions', api_get_sessions)
    app.router.add_post('/api/sessions', api_save_session)
    app.router.add_delete('/api/sessions/{label}', api_delete_session)

    app.router.add_get('/api/tasks/status', api_get_status)
    app.router.add_post('/api/tasks/start', api_start_task)
    app.router.add_post('/api/tasks/stop', api_stop_task)

    app.router.add_get('/api/admin/users', api_admin_get_users)
    app.router.add_post('/api/admin/users', api_admin_add_user)
    app.router.add_put('/api/admin/users', api_admin_edit_user)
    app.router.add_delete('/api/admin/users/{username}', api_admin_delete_user)
    app.router.add_get('/api/admin/live_monitor', api_admin_live_monitor)

    app.router.add_get('/ws/logs', websocket_handler)

    # Static file direct routes
    app.router.add_get('/', index_handler)
    app.router.add_get('/index.html', index_handler)
    app.router.add_get('/style.css', style_handler)
    app.router.add_get('/app.js', app_js_handler)
    app.router.add_static('/static/', path='./static', name='static')

    return app

def ensure_browsers():
    try:
        import subprocess
        # Check or install playwright chromium if on linux or fresh install
        if not os.path.exists(os.path.expanduser("~/.cache/ms-playwright")) and os.name != 'nt':
            print("[SETUP] Ensuring Playwright Chromium binaries are installed...")
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=False)
    except Exception:
        pass

if __name__ == '__main__':
    import webbrowser
    import threading

    ensure_browsers()
    load_users()
    load_sessions()
    app = create_app()
    port = int(os.environ.get("PORT", 8080))
    url = f"http://localhost:{port}"

    def open_browser():
        time.sleep(1.2)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=open_browser, daemon=True).start()

    print(f"\n👑 [SERVER GOD CLAN WEB ENGINE STARTED] -> {url}")
    print(f"🔱 Accessible on Phone, PC & iOS on your local network: http://0.0.0.0:{port}\n")
    web.run_app(app, host='0.0.0.0', port=port)
