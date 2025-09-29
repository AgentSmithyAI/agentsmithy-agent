from __future__ import annotations

from typing import Any

import aiohttp
from playwright.async_api import async_playwright
from pydantic import BaseModel, Field, HttpUrl

from agentsmithy_server.config import settings

from ..base_tool import BaseTool


class WebFetchArgs(BaseModel):
    url: HttpUrl = Field(
        ..., description="URL to fetch. Automatically chooses HTTP or JS render."
    )


class WebFetchTool(BaseTool):
    name: str = "web_fetch"
    description: str = (
        "Fetch a web page with a minimal API. Uses fast HTTP fetch first, and falls back "
        "to JavaScript rendering (Playwright) only if needed."
    )
    args_schema: type[BaseModel] | dict[str, Any] | None = WebFetchArgs

    async def _arun(self, **kwargs: Any) -> dict[str, Any]:
        args = WebFetchArgs(**kwargs)
        # Step 1: Try plain HTTP fetch quickly
        http_res = await self._fetch_http(args)

        if http_res.get("type") == "web_browse_result":
            # If we successfully fetched text-like content, decide if this is good enough
            content_type = (http_res.get("content_type") or "").lower()
            text: str | None = http_res.get("text")
            status = http_res.get("status")

            if status == 200 and text:
                # Heuristics: if the page clearly requires JS, fall back to JS render
                lowered = text.lower()
                requires_js_markers = (
                    "please enable javascript" in lowered
                    or "requires javascript" in lowered
                    or "<noscript>" in lowered
                )
                # Very short HTML often indicates client-only shells
                is_suspiciously_short = len(text) < 512 and "<html" in lowered

                if ("html" in content_type) and (
                    requires_js_markers or is_suspiciously_short
                ):
                    pass
                else:
                    return http_res
            else:
                # HTTP returned non-text or empty; try JS as fallback
                pass
        else:
            # HTTP failed (timeout/network/etc.). Try JS before giving up.
            pass

        # Step 2: JS rendering fallback (Playwright must be installed)
        js_res = await self._render_js(args)
        if js_res.get("type") == "web_browse_result":
            return js_res
        # If JS also failed, return the HTTP error/result as best-effort
        return http_res

    async def _fetch_http(self, args: WebFetchArgs) -> dict[str, Any]:
        timeout = aiohttp.ClientTimeout(total=12.0)
        headers = {"User-Agent": settings.web_user_agent}
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            try:
                async with session.get(str(args.url), allow_redirects=True) as resp:
                    content_type = resp.headers.get("Content-Type", "")
                    status = resp.status
                    final_url = str(resp.url)
                    raw = await resp.read()
                    encoding = resp.charset or "utf-8"

                    text: str | None = None
                    if (
                        "text/" in content_type
                        or "html" in content_type
                        or "json" in content_type
                        or "xml" in content_type
                    ) and status == 200:
                        try:
                            text = raw.decode(encoding, errors="replace")
                        except Exception:
                            text = None

                    return {
                        "type": "web_browse_result",
                        "mode": "http",
                        "url": str(args.url),
                        "final_url": final_url,
                        "status": status,
                        "content_type": content_type,
                        "encoding": encoding,
                        "text": text,
                    }
            except TimeoutError:
                return {
                    "type": "web_browse_error",
                    "mode": "http",
                    "url": str(args.url),
                    "error": "HTTP timeout",
                    "error_type": "Timeout",
                }
            except Exception as e:
                return {
                    "type": "web_browse_error",
                    "mode": "http",
                    "url": str(args.url),
                    "error": str(e),
                    "error_type": type(e).__name__,
                }

    async def _render_js(self, args: WebFetchArgs) -> dict[str, Any]:
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(user_agent=settings.web_user_agent)
                page = await context.new_page()
                # Keep tight time budget to avoid hanging renders
                page.set_default_navigation_timeout(5000)
                page.set_default_timeout(5000)

                response = await page.goto(str(args.url), wait_until="domcontentloaded")
                try:
                    await page.wait_for_load_state("networkidle", timeout=2000)
                except Exception:
                    pass

                final_url = page.url
                status = response.status if response is not None else None
                content_type = None
                try:
                    if response is not None:
                        headers = await response.all_headers()
                        content_type = headers.get("content-type")
                except Exception:
                    pass

                html = await page.content()

                await context.close()
                await browser.close()

                return {
                    "type": "web_browse_result",
                    "mode": "js",
                    "url": str(args.url),
                    "final_url": final_url,
                    "status": status,
                    "content_type": content_type or "text/html",
                    "text": html,
                }
        except Exception as e:
            return {
                "type": "web_browse_error",
                "mode": "js",
                "url": str(args.url),
                "error": str(e),
                "error_type": type(e).__name__,
            }
