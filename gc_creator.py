import asyncio
import json
import os
import random
import shutil
import sys
import time
import urllib.parse
from playwright.async_api import async_playwright

SESSION_FILE = "saved_sessions.json"

def clear():
    os.system('cls' if os.name == 'nt' else 'clear')

def professional_banner():
    clear()
    banner = """\033[1;35m
    ███████╗███████╗██████╗ ██╗   ██╗███████╗██████╗      ██████╗  ██████╗ ██████╗ 
    ██╔════╝██╔════╝██╔══██╗██║   ██║██╔════╝██╔══██╗    ██╔════╝ ██╔═══██╗██╔══██╗
    ███████╗█████╗  ██████╔╝██║   ██║█████╗  ██████╔╝    ██║  ███╗██║   ██║██║  ██║
    ╚════██║██╔══╝  ██╔══██╗╚██╗ ██╔╝██╔══╝  ██╔══██╗    ██║   ██║██║   ██║██║  ██║
    ███████║███████╗██║  ██║ ╚████╔╝ ███████╗██║  ██║    ╚██████╔╝╚██████╔╝██████╔╝
    ╚══════╝╚══════╝╚═╝  ╚═╝  ╚═══╝  ╚══════╝╚═╝  ╚═╝     ╚═════╝  ╚═════╝ ╚═════╝ 
\033[1;36m       👑══════════════════════════════════════════════════════════════════════👑
\033[1;37m        🔱✦ SERVER GOD CLAN GC CREATOR SCRIPT BY KING ✦🔱
\033[1;33m        ⚡ DEVELOPER ✦ KING | THE ABSOLUTE GOD CLAN ✦
\033[1;32m        ⚡ STATUS    ✦ TARGET GROUP INJECTION ACTIVE ✦
\033[1;36m       👑══════════════════════════════════════════════════════════════════════👑\033[0m
"""
    print(banner)

def load_saved_sessions():
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_session(label, sessionid):
    sessions = load_saved_sessions()
    sessions[label] = sessionid.strip()
    try:
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(sessions, f, indent=4)
        print(f"\033[1;32m    💾 [SESSION SAVED] '{label}' saved successfully!\033[0m")
    except Exception as e:
        print(f"\033[1;31m    ⚠️ [ERROR] Failed to save session: {e}\033[0m")

def select_session():
    saved = load_saved_sessions()
    if saved:
        print("\033[1;33m    📁 [SAVED SESSIONS FOUND]:\033[0m")
        labels = list(saved.keys())
        for idx, lbl in enumerate(labels, 1):
            print(f"      [{idx}] {lbl}")
        print("      [N] Add New Session ID")
        
        choice = input("\n\033[1;37m    🔱 Choose option (1/2/... or N): \033[0m").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(labels):
            selected_key = labels[int(choice) - 1]
            print(f"\033[1;32m    ✅ Using saved session: {selected_key}\033[0m")
            return saved[selected_key]
    
    # New session
    sid = input("\n\033[1;37m    🔱 ENTER INSTAGRAM SESSIONID COOKIE: \033[0m").strip()
    lbl = input("    🔱 GIVE A NAME/LABEL FOR THIS SESSION TO SAVE IT: ").strip() or f"User_{random.randint(100,999)}"
    save_session(lbl, sid)
    return sid

async def block_media(route):
    if route.request.resource_type in ["image", "media"]:
        await route.abort()
    else:
        await route.continue_()

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
            if await btn.is_visible(timeout=1000):
                await btn.click(force=True)
                await asyncio.sleep(0.8)
        except Exception:
            pass

def get_search_input(page):
    return page.locator('input[placeholder*="Search" i], input[name="queryBox"], input[name="searchInput"], input[aria-label*="Search" i], div[role="dialog"] input[type="text"], div[role="dialog"] input').first

async def open_new_message_modal(page):
    await dismiss_popups(page)
    
    # Check if modal is already open
    dialog = page.locator('div[role="dialog"]')
    search_input = dialog.locator('input[type="text"], input[name="queryBox"], input[placeholder*="Search" i]').first
    if await search_input.is_visible(timeout=1500):
        return True

    # 1. Click pencil or Send Message button in current view
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

    # 2. Go to inbox directly and click button
    await safe_goto(page, "https://www.instagram.com/direct/inbox/")
    await asyncio.sleep(2.5)
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

async def create_single_gc(page, gc_num, gc_name, members):
    print(f"\n\033[1;36m    🚀 [GC #{gc_num}] Starting Group Creation: '{gc_name}'...\033[0m")
    try:
        # Step 1: Open New Message Dialog
        opened = await open_new_message_modal(page)
        if not opened:
            print(f"      \033[1;31m❌ Could not open New Message modal.\033[0m")
            return False

        dialog = page.locator('div[role="dialog"]')
        search_input = dialog.locator('input[type="text"], input[name="queryBox"], input[placeholder*="Search" i]').first
        await search_input.wait_for(state="visible", timeout=8000)

        added_count = 0
        valid_members_added = []

        # Step 2: Search & select members inside the dialog
        for member in members:
            print(f"      🔍 Searching member: @{member}")
            try:
                search_input = dialog.locator('input[type="text"], input[name="queryBox"], input[placeholder*="Search" i]').first
                await search_input.click(force=True)
                await page.keyboard.press("Control+A")
                await page.keyboard.press("Backspace")
                await asyncio.sleep(0.3)

                await page.keyboard.type(member, delay=60)
                await asyncio.sleep(3.5)

                added = False

                # 1. Search for username row in dialog
                try:
                    user_target = dialog.locator(f'span:text-is("{member}"), span:has-text("{member}"), div[role="button"]:has-text("{member}")').first
                    if await user_target.is_visible(timeout=2500):
                        await user_target.click(force=True)
                        added = True
                except Exception:
                    pass

                # 2. Checkboxes in search dialog
                if not added:
                    try:
                        checkboxes = dialog.locator('input[type="checkbox"], svg[aria-label="Toggle checkbox"]')
                        if await checkboxes.count() > 0:
                            await checkboxes.first.click(force=True)
                            added = True
                    except Exception:
                        pass

                # 3. Fallback: keyboard Enter/Space
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
                    print(f"      \033[1;32m✅ [VALID] Selected @{member}\033[0m")
                    added_count += 1
                    valid_members_added.append(member)
                else:
                    print(f"      \033[1;31m❌ [NOT FOUND] Could not select @{member}\033[0m")

            except Exception as ex:
                print(f"      ⚠️ Search error for @{member}: {ex}")
            
            await asyncio.sleep(1.5)

        if added_count < 2:
            print(f"\n      \033[1;31m⛔ [GC ABORTED] Minimum 2 valid members required! (Found: {valid_members_added})\033[0m")
            return False

        # Step 3: Click the blue "Chat" button inside dialog
        await asyncio.sleep(1.5)
        chat_btns = dialog.locator('div[role="button"]:has-text("Chat"), button:has-text("Chat"), div[role="button"]:has-text("Create chat"), button:has-text("Create chat")')
        if await chat_btns.count() > 0 and await chat_btns.last.is_visible():
            await chat_btns.last.click(force=True)
            print(f"      👉 Clicked 'Chat' button...")
        else:
            await page.keyboard.press("Enter")
            print(f"      👉 Pressed Enter to confirm chat...")

        await asyncio.sleep(4)

        # Step 4: Send first message to officially create & activate the group thread
        msg_box = page.locator('div[role="textbox"], div[aria-label*="Message" i], div[contenteditable="true"], textarea[placeholder*="Message" i]').first
        if await msg_box.is_visible(timeout=8000):
            await msg_box.click(force=True)
            await page.keyboard.type("👑 SERVER GOD CLAN GC CREATED", delay=25)
            await asyncio.sleep(0.8)
            
            send_btn = page.locator('div[role="button"]:has-text("Send"), button:has-text("Send")').first
            if await send_btn.is_visible(timeout=2000):
                await send_btn.click(force=True)
            else:
                await page.keyboard.press("Enter")
                
            print(f"      🚀 Sent initial message to activate GC!")
            await asyncio.sleep(2)

        # Confirm thread created
        if "/direct/t/" in page.url:
            thread_id = page.url.split("/direct/t/")[-1].strip("/")
            print(f"      \033[1;32m✅ [THREAD ACTIVE] Thread ID: {thread_id}\033[0m")

        # Step 5: Change Group Name (if specified)
        if gc_name:
            try:
                # Open Details if needed
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
                        if await d_btn.is_visible(timeout=2000):
                            await d_btn.click(force=True)
                            await asyncio.sleep(2)
                            break
                    except Exception:
                        continue

                change_btn = page.locator('div[role="button"]:has-text("Change"), button:has-text("Change")').first
                if await change_btn.is_visible(timeout=3000):
                    await change_btn.click(force=True)
                    await asyncio.sleep(1.5)
                    
                    rename_input = page.locator('div[role="dialog"] input[type="text"], input[name="change-group-name"], input[placeholder*="Group name" i]').first
                    if await rename_input.is_visible(timeout=3000):
                        await rename_input.click(force=True)
                        await page.keyboard.press("Control+A")
                        await page.keyboard.press("Backspace")
                        await page.keyboard.type(gc_name, delay=35)
                        await asyncio.sleep(0.5)
                        
                        save_btn = page.locator('div[role="dialog"] div[role="button"]:has-text("Save"), div[role="dialog"] button:has-text("Save")').first
                        if await save_btn.is_visible(timeout=2000):
                            await save_btn.click(force=True)
                        else:
                            await page.keyboard.press("Enter")
                        print(f"      🏷️  Group Name set to: '{gc_name}'")
                        await asyncio.sleep(1.5)
            except Exception as e:
                print(f"      ⚠️ Rename notice: {e}")

        print(f"\033[1;32m    🎉 [SUCCESS] GC #{gc_num} Created & Configured successfully!\033[0m")
        return True

    except Exception as e:
        print(f"\033[1;31m    ❌ [ERROR] GC #{gc_num} creation failed: {e}\033[0m")
        return False

async def main():
    professional_banner()
    
    # 1. Session selection / login
    sid = select_session()
    
    # 2. User Inputs
    print("\n\033[1;37m    ━━━━━━━━━━━━━━━━ CONFIGURATION ━━━━━━━━━━━━━━━━\033[0m")
    gc_count = int(input("    🔱 KITNE GC BANANE HAI? (GC Count): ").strip() or "1")
    gc_name_prefix = input("    🔱 GC KA NAME / TITLE KYA RAKHNA HAI?: ").strip() or "GC BY KING"
    
    raw_users = input("    🔱 USERNAMES DAALO (Comma separated, at least 2 users): ").strip()
    members = [u.strip().lstrip('@') for u in raw_users.split(',') if u.strip()]
    
    if len(members) < 2:
        print("\033[1;31m    ⚠️ Minimum 2 usernames required to form a group!\033[0m")
        extra = input("    🔱 Enter additional username(s) separated by comma: ").strip()
        members.extend([u.strip().lstrip('@') for u in extra.split(',') if u.strip()])
    
    delay_between = int(input("    🔱 DELAY BETWEEN GC CREATION (Seconds, default 5): ").strip() or "5")
    headless_choice = input("    🔱 RUN IN BACKGROUND / HEADLESS? (y/n, default n): ").strip().lower()
    is_headless = headless_choice in ['y', 'yes']

    print("\n\033[1;32m    [SYSTEM] INITIALIZING BROWSER ENGINE...\033[0m")
    
    user_data_dir = "./gc_bot_browser_session"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir,
            headless=is_headless,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="en-US",
            timezone_id="Asia/Kolkata",
            args=[
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--start-maximized"
            ]
        )
        
        clean_sid = urllib.parse.unquote(sid.strip())
        user_id = clean_sid.split(":")[0] if ":" in clean_sid else ""

        cookies = [
            {
                "name": "sessionid",
                "value": clean_sid,
                "domain": ".instagram.com",
                "path": "/",
                "secure": True,
                "httpOnly": True
            }
        ]
        if user_id.isdigit():
            cookies.append({
                "name": "ds_user_id",
                "value": user_id,
                "domain": ".instagram.com",
                "path": "/",
                "secure": True,
                "httpOnly": False
            })
        await browser.add_cookies(cookies)
        
        page = browser.pages[0] if browser.pages else await browser.new_page()
        await page.route("**/*", block_media)
        
        print("\033[1;32m    🔑 LOGGING INTO INSTAGRAM DIRECT INBOX...\033[0m")
        await safe_goto(page, "https://www.instagram.com/direct/inbox/")
        await asyncio.sleep(3)
        await dismiss_popups(page)

        # Check if logged in
        login_form_count = await page.locator('input[name="password"], input[name="emailOrUsername"], input[name="username"], button[type="submit"]:has-text("Log in"), button:has-text("Log In")').count()
        inbox_nav_count = await page.locator('svg[aria-label="Direct"], svg[aria-label="Messages"], a[href*="/direct/"], input[placeholder*="Search" i]').count()
        
        if login_form_count > 0 or ("accounts/login" in page.url) or (page.url.rstrip("/") == "https://www.instagram.com" and inbox_nav_count == 0):
            print("\n\033[1;31m    ❌ [LOGIN FAILED] Invalid or expired session ID!")
            print("    💡 Instagram redirected to login page. Please provide a fresh 'sessionid' cookie.\033[0m\n")
            await browser.close()
            return

        print("\033[1;32m    ✅ [LOGIN SUCCESS] Connected to Instagram Inbox!\033[0m")
        
        success_count = 0
        failed_count = 0

        # Start GC creation loop
        for i in range(1, gc_count + 1):
            current_gc_name = f"{gc_name_prefix} #{i}" if gc_count > 1 else gc_name_prefix
            result = await create_single_gc(page, i, current_gc_name, members)
            
            if result:
                success_count += 1
            else:
                failed_count += 1

            # LIVE STATS DISPLAY
            print(f"\n\033[1;33m    📊 [LIVE STATS] TOTAL: {gc_count} | ✅ CREATED: {success_count} | ❌ FAILED: {failed_count}\033[0m")

            if i < gc_count:
                print(f"    ⏳ Waiting {delay_between} seconds before creating next GC...\n")
                await asyncio.sleep(delay_between)

        print("\n\033[1;36m    👑═════════════════ FINAL REPORT ═════════════════👑")
        print(f"     🔱 TOTAL REQUESTED : {gc_count}")
        print(f"     ✅ SUCCESSFULLY GC : {success_count}")
        print(f"     ❌ FAILED GC       : {failed_count}")
        print("    👑═════════════════════════════════════════════════👑\033[0m")
        await asyncio.sleep(3)
        await browser.close()
        
        if os.path.exists(user_data_dir):
            shutil.rmtree(user_data_dir, ignore_errors=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\033[1;31m    🔱 SCRIPT STOPPED BY USER. \033[0m")
        sys.exit()
