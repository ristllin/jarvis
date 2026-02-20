"""
Browser Agent - Multi-turn LLM subagent for web automation via Playwright.
"""

import asyncio
import json
import os
import re
from datetime import UTC, datetime

from jarvis.observability.logger import get_logger

log = get_logger("browser_agent")
SCREENSHOT_DIR = "/data/browser_screenshots"

BROWSER_PRIMITIVES = (
    "Respond with ONE JSON object per turn.\n"
    "\nActions: navigate, click, type, screenshot, extract_text, extract_html,\n"
    "wait_for_element, select, hover, scroll, get_url, go_back, go_forward,\n"
    "evaluate, get_elements, fill_form, press_key, wait, done.\n"
    "\nExamples:\n"
    '{"action":"navigate","url":"https://x.com","wait_until":"networkidle"}\n'
    '{"action":"click","selector":"button#go"} or {"action":"click","text":"Sign In"}\n'
    '{"action":"type","selector":"#q","text":"hello","clear":true,"press_enter":true}\n'
    '{"action":"screenshot","full_page":true}\n'
    '{"action":"extract_text","selector":"#res","max_length":5000}\n'
    '{"action":"extract_html","selector":"#c","outer":true}\n'
    '{"action":"wait_for_element","selector":".r","state":"visible","timeout":10000}\n'
    '{"action":"select","selector":"select#c","value":"US"}\n'
    '{"action":"hover","selector":".dd"}\n'
    '{"action":"scroll","direction":"down","amount":500}\n'
    '{"action":"get_url"} {"action":"go_back"} {"action":"go_forward"}\n'
    '{"action":"evaluate","script":"document.title"}\n'
    '{"action":"get_elements","selector":"a","max_count":20}\n'
    '{"action":"fill_form","fields":{"#n":"Jo","#e":"j@x.com"}}\n'
    '{"action":"press_key","key":"Enter"}\n'
    '{"action":"wait","duration":2000}\n'
    '{"action":"done","summary":"Done.","data":{"k":"v"}}\n'
    "\nRules: ONE action/turn. You see result+page state after each.\n"
    "Use extract_text/get_elements before clicking. wait_for_element for dynamic content.\n"
)


class BrowserAgent:
    def __init__(self, llm_router, blob_storage=None):
        self.router = llm_router
        self.blob = blob_storage
        self._browser = self._context = self._page = self._playwright = None

    async def run(
        self,
        task,
        start_url=None,
        system_prompt=None,
        tier="coding_level2",
        max_turns=30,
        temperature=0.2,
        headless=True,
        viewport=None,
        continuation_context=None,
        cookies=None,
        headers=None,
    ):
        log.info("browser_agent_start", task=task[:100], tier=tier, max_turns=max_turns)
        if self.blob:
            self.blob.store(
                event_type="browser_agent_start",
                content=f"Task: {task}",
                metadata={"tier": tier, "max_turns": max_turns, "start_url": start_url, "headless": headless},
            )
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)
        ss, pgs, data, acts = [], [], {}, []
        try:
            await self._launch(headless, viewport, cookies, headers)
            if start_url:
                await self._page.goto(start_url, wait_until="domcontentloaded", timeout=30000)
                pgs.append(start_url)
            msgs = self._init_msgs(task, start_url, system_prompt, continuation_context, await self._page_state())
            return await self._loop(msgs, max_turns, tier, temperature, ss, pgs, data, acts)
        except Exception as e:
            log.error("browser_agent_fatal", error=str(e))
            p = await self._screenshot("fatal")
            if p:
                ss.append(p)
            return {
                "success": False,
                "summary": f"Failed: {e}",
                "turns": len(acts),
                "pages_visited": pgs,
                "screenshots": ss,
                "actions": acts,
                "extracted_data": data,
            }
        finally:
            await self._cleanup()

    def _init_msgs(self, task, url, custom, cont, ps):
        sp = self._sys_prompt(custom)
        if cont:
            m = [{"role": "system", "content": sp}] + list(cont[-20:])
            m.append({"role": "user", "content": f"Resume: {task}\n\n## Page\n{ps}"})
            return m
        u = f"## Task\n{task}\n\n"
        u += f"At: {url}\n\n" if url else "Browser open (blank).\n\n"
        u += f"## Page\n{ps}\n\nBegin."
        return [{"role": "system", "content": sp}, {"role": "user", "content": u}]

    async def _loop(self, msgs, mt, tier, temp, ss, pgs, data, acts):
        for t in range(mt):
            try:
                r = await self.router.complete(
                    messages=msgs,
                    tier=tier,
                    temperature=temp,
                    max_tokens=4096,
                    task_description=f"browser_agent:turn_{t}",
                )
                c = r.content or ""
                if not c.strip():
                    msgs += [
                        {"role": "assistant", "content": "(empty)"},
                        {"role": "user", "content": "Send JSON action or done."},
                    ]
                    continue
                act = self._parse(c)
                if not act:
                    msgs += [
                        {"role": "assistant", "content": c},
                        {"role": "user", "content": "JSON action please. done if finished."},
                    ]
                    continue
                an = act.get("action", "")
                log.info("browser_agent_action", turn=t, action=an)
                if an == "done":
                    p = await self._screenshot("final")
                    if p:
                        ss.append(p)
                    return self._done_result(act, t, ss, pgs, data, acts)
                rt = await self._exec(act)
                acts.append({"action": an, "turn": t, "params": {k: v for k, v in act.items() if k != "action"}})
                if an == "navigate":
                    pgs.append(act.get("url", ""))
                if an == "screenshot" and rt.startswith("Screenshot saved:"):
                    ss.append(rt.split(": ", 1)[1])
                ps = await self._page_state()
                msgs += [
                    {"role": "assistant", "content": json.dumps(act)},
                    {"role": "user", "content": f"Result:\n{rt[:6000]}\n\n## Page\n{ps}"},
                ]
                if len(msgs) > 40:
                    msgs = msgs[:1] + msgs[-30:]
                msgs = [m if m.get("content") else {**m, "content": "(c)"} for m in msgs]
            except Exception as e:
                log.error("browser_turn_err", turn=t, error=str(e))
                p = await self._screenshot(f"err_{t}")
                if p:
                    ss.append(p)
                msgs.append({"role": "user", "content": f"Error: {e}\nContinue or done."})
        return {
            "success": False,
            "summary": f"Max turns ({mt}).",
            "turns": mt,
            "pages_visited": pgs,
            "screenshots": ss,
            "actions": acts,
            "extracted_data": data,
            "continuation_context": msgs[-20:],
            "can_continue": True,
        }

    def _done_result(self, act, t, ss, pgs, data, acts):
        s = act.get("summary", "Done.")
        d = act.get("data", {})
        if d:
            data.update(d)
        log.info("browser_agent_done", turns=t + 1, summary=s[:200])
        if self.blob:
            self.blob.store(
                event_type="browser_agent_done",
                content=f"{s}\nTurns:{t + 1}",
                metadata={"turns": t + 1, "pages_visited": pgs},
            )
        return {
            "success": True,
            "summary": s,
            "turns": t + 1,
            "pages_visited": pgs,
            "screenshots": ss,
            "actions": acts,
            "extracted_data": data,
        }

    def _sys_prompt(self, custom=None):
        p = [
            "You are a browser automation agent, a subagent of JARVIS.",
            "You control a Chromium browser via Playwright.",
            "",
        ]
        if custom:
            p.append(f"## Instructions\n{custom}\n")
        p.append(BROWSER_PRIMITIVES)
        return "\n".join(p)

    def _parse(self, c):
        for fn in [
            lambda: json.loads(c),
            lambda: json.loads(re.search(r"```(?:json)?\s*\n?(.*?)\n?```", c, re.DOTALL).group(1)),
            lambda: json.loads(c[c.find("{") : c.rfind("}") + 1]),
        ]:
            try:
                return fn()
            except Exception:
                pass
        return None

    async def _launch(self, headless, viewport, cookies, headers):
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=headless, args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        vp = viewport or {"width": 1280, "height": 720}
        kw = {"viewport": vp}
        if headers:
            kw["extra_http_headers"] = headers
        self._context = await self._browser.new_context(**kw)
        if cookies:
            await self._context.add_cookies(cookies)
        self._page = await self._context.new_page()
        log.info("browser_launched", headless=headless)

    async def _cleanup(self):
        try:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            log.warning("browser_close_err", error=str(e))
        self._browser = self._context = self._page = self._playwright = None

    async def _page_state(self):
        try:
            url = self._page.url
            title = await self._page.title()
            txt = await self._page.evaluate("document.body ? document.body.innerText.substring(0,1500) : '(empty)'")
            return f"URL: {url}\nTitle: {title}\nText:\n{txt[:1500]}"
        except Exception as e:
            return f"Page state error: {e}"

    async def _screenshot(self, label="ss"):
        try:
            ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            path = os.path.join(SCREENSHOT_DIR, f"{label}_{ts}.png")
            await self._page.screenshot(path=path)
            return path
        except Exception:
            return None

    async def _exec(self, action):
        n = action.get("action", "")
        try:
            h = getattr(self, f"_act_{n}", None)
            if h:
                return await h(action)
            return f"Unknown action: {n}"
        except Exception as e:
            p = await self._screenshot(f"err_{n}")
            msg = f"Action '{n}' failed: {e}"
            if p:
                msg += f"\nError screenshot: {p}"
            return msg

    async def _act_navigate(self, a):
        url = a.get("url", "")
        wu = a.get("wait_until", "domcontentloaded")
        await self._page.goto(url, wait_until=wu, timeout=30000)
        return f"Navigated to {url}"

    async def _act_click(self, a):
        sel = a.get("selector")
        text = a.get("text")
        to = a.get("timeout", 5000)
        if text:
            loc = self._page.get_by_text(text, exact=False).first
            await loc.click(timeout=to)
            return f"Clicked text: {text}"
        await self._page.click(sel, timeout=to)
        return f"Clicked: {sel}"

    async def _act_type(self, a):
        sel = a.get("selector", "")
        txt = a.get("text", "")
        if a.get("clear"):
            await self._page.fill(sel, "")
        await self._page.fill(sel, txt)
        if a.get("press_enter"):
            await self._page.press(sel, "Enter")
        return f"Typed into {sel}"

    async def _act_screenshot(self, a):
        sel = a.get("selector")
        fp = a.get("full_page", False)
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        path = os.path.join(SCREENSHOT_DIR, f"ss_{ts}.png")
        if sel:
            el = await self._page.query_selector(sel)
            if el:
                await el.screenshot(path=path)
            else:
                return f"Element not found: {sel}"
        else:
            await self._page.screenshot(path=path, full_page=fp)
        return f"Screenshot saved: {path}"

    async def _act_extract_text(self, a):
        sel = a.get("selector")
        ml = a.get("max_length", 8000)
        if sel:
            el = await self._page.query_selector(sel)
            if not el:
                return f"Element not found: {sel}"
            txt = await el.inner_text()
        else:
            txt = await self._page.evaluate("document.body ? document.body.innerText : '(empty)'")
        return txt[:ml]

    async def _act_extract_html(self, a):
        sel = a.get("selector")
        outer = a.get("outer", False)
        if sel:
            el = await self._page.query_selector(sel)
            if not el:
                return f"Element not found: {sel}"
            if outer:
                html = await el.evaluate("e => e.outerHTML")
            else:
                html = await el.inner_html()
        else:
            html = await self._page.content()
        return html[:10000]

    async def _act_wait_for_element(self, a):
        sel = a.get("selector", "")
        state = a.get("state", "visible")
        to = a.get("timeout", 10000)
        await self._page.wait_for_selector(sel, state=state, timeout=to)
        return f"Element found: {sel} (state={state})"

    async def _act_select(self, a):
        sel = a.get("selector", "")
        val = a.get("value")
        label = a.get("label")
        if val:
            await self._page.select_option(sel, value=val)
            return f"Selected value={val} in {sel}"
        if label:
            await self._page.select_option(sel, label=label)
            return f"Selected label={label} in {sel}"
        return "No value or label provided for select"

    async def _act_hover(self, a):
        sel = a.get("selector", "")
        await self._page.hover(sel)
        return f"Hovered: {sel}"

    async def _act_scroll(self, a):
        direction = a.get("direction", "down")
        amount = a.get("amount", 500)
        sel = a.get("selector")
        if direction == "bottom":
            await self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            return "Scrolled to bottom"
        if direction == "top":
            await self._page.evaluate("window.scrollTo(0, 0)")
            return "Scrolled to top"
        dy = amount if direction == "down" else -amount
        if sel:
            await self._page.evaluate(f"document.querySelector('{sel}').scrollBy(0, {dy})")
        else:
            await self._page.evaluate(f"window.scrollBy(0, {dy})")
        return f"Scrolled {direction} by {amount}px"

    async def _act_get_url(self, a):
        return f"Current URL: {self._page.url}"

    async def _act_go_back(self, a):
        await self._page.go_back(timeout=15000)
        return f"Went back to: {self._page.url}"

    async def _act_go_forward(self, a):
        await self._page.go_forward(timeout=15000)
        return f"Went forward to: {self._page.url}"

    async def _act_evaluate(self, a):
        script = a.get("script", "")
        result = await self._page.evaluate(script)
        return f"Result: {json.dumps(result) if result is not None else 'undefined'}"

    async def _act_get_elements(self, a):
        sel = a.get("selector", "")
        mc = a.get("max_count", 20)
        els = await self._page.query_selector_all(sel)
        infos = []
        for i, el in enumerate(els[:mc]):
            tag = await el.evaluate("e => e.tagName.toLowerCase()")
            txt = (await el.inner_text())[:100] if await el.is_visible() else ""
            href = await el.get_attribute("href") or ""
            infos.append({"index": i, "tag": tag, "text": txt.strip(), "href": href})
        return json.dumps(infos, indent=2)

    async def _act_fill_form(self, a):
        fields = a.get("fields", {})
        filled = []
        for sel, val in fields.items():
            await self._page.fill(sel, val)
            filled.append(sel)
        return f"Filled {len(filled)} fields: {filled}"

    async def _act_press_key(self, a):
        key = a.get("key", "Enter")
        await self._page.keyboard.press(key)
        return f"Pressed: {key}"

    async def _act_wait(self, a):
        dur = a.get("duration", 1000)
        await asyncio.sleep(dur / 1000.0)
        return f"Waited {dur}ms"
