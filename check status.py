# Check status
import argparse
import csv
import time
from collections import deque
from dataclasses import dataclass, asdict
from typing import Optional, Set, Tuple
from urllib.parse import urljoin, urldefrag, urlparse
import requests
from bs4 import BeautifulSoup
import urllib.robotparser as robotparser


@dataclass
class PageResult:
    url: str
    final_url: str
    status: Optional[int]
    ok: bool
    error: Optional[str]
    elapsed_ms: Optional[int]
    content_type: Optional[str]
    redirected: bool
    redirect_chain: str
    depth: int
    title: Optional[str]


DEFAULT_UA = (
    "Mozilla/5.0 (compatible; LinkHealthChecker/1.0; +https://example.invalid/bot)"
)


def is_http_url(u: str) -> bool:
    try:
        p = urlparse(u)
        return p.scheme in ("http", "https")
    except Exception:
        return False


def normalize_url(base: str, link: str) -> Optional[str]:
    if not link:
        return None
    link = link.strip()
    lowers = link.lower()
    if lowers.startswith(("javascript:", "mailto:", "tel:", "sms:", "data:")):
        return None
    abs_url = urljoin(base, link)
    abs_url, _ = urldefrag(abs_url)
    if not is_http_url(abs_url):
        return None
    return abs_url


def same_site(a: str, b: str) -> bool:
    pa, pb = urlparse(a), urlparse(b)
    return (pa.scheme, pa.hostname, pa.port) == (pb.scheme, pb.hostname, pb.port)


def get_title(html: str) -> Optional[str]:
    try:
        soup = BeautifulSoup(html, "html.parser")
        t = soup.find("title")
        if t and t.text:
            return t.text.strip()[:200]
    except Exception:
        pass
    return None


def fetch(
    session: requests.Session,
    url: str,
    timeout: float,
    verify_ssl: bool,
) -> PageResult:
    t0 = time.time()
    try:
        resp = session.get(url, timeout=timeout, allow_redirects=True, verify=verify_ssl, stream=True)
        raw_html = ""
        content_type = resp.headers.get("Content-Type", "")
        if "text/html" in content_type.lower():
            try:
                raw_html = resp.raw.read(128 * 1024, decode_content=True)
                if isinstance(raw_html, bytes):
                    raw_html = raw_html.decode(resp.encoding or "utf-8", errors="replace")
            except Exception:
                raw_html = ""
        title = get_title(raw_html) if raw_html else None

        elapsed_ms = int((time.time() - t0) * 1000)
        history = " -> ".join([r.url for r in resp.history] + [resp.url]) if resp.history else ""
        return PageResult(
            url=url,
            final_url=str(resp.url),
            status=resp.status_code,
            ok=200 <= resp.status_code < 400,
            error=None,
            elapsed_ms=elapsed_ms,
            content_type=content_type or None,
            redirected=bool(resp.history),
            redirect_chain=history,
            depth=0,
            title=title,
        )
    except requests.exceptions.SSLError as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        return PageResult(url=url, final_url=url, status=None, ok=False, error=f"SSL error: {e}", elapsed_ms=elapsed_ms,
                          content_type=None, redirected=False, redirect_chain="", depth=0, title=None)
    except requests.exceptions.ConnectTimeout:
        elapsed_ms = int((time.time() - t0) * 1000)
        return PageResult(url=url, final_url=url, status=None, ok=False, error="Connection timeout",
                          elapsed_ms=elapsed_ms, content_type=None, redirected=False, redirect_chain="", depth=0, title=None)
    except requests.exceptions.ReadTimeout:
        elapsed_ms = int((time.time() - t0) * 1000)
        return PageResult(url=url, final_url=url, status=None, ok=False, error="Read timeout",
                          elapsed_ms=elapsed_ms, content_type=None, redirected=False, redirect_chain="", depth=0, title=None)
    except requests.exceptions.ConnectionError as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        return PageResult(url=url, final_url=url, status=None, ok=False, error=f"Connection error: {e}",
                          elapsed_ms=elapsed_ms, content_type=None, redirected=False, redirect_chain="", depth=0, title=None)
    except Exception as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        return PageResult(url=url, final_url=url, status=None, ok=False, error=f"Error: {e}",
                          elapsed_ms=elapsed_ms, content_type=None, redirected=False, redirect_chain="", depth=0, title=None)


def extract_links(html_bytes: bytes, base_url: str, encoding: Optional[str]) -> Set[str]:
    links: Set[str] = set()
    try:
        html = html_bytes.decode(encoding or "utf-8", errors="replace")
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            norm = normalize_url(base_url, a["href"])
            if norm:
                links.add(norm)
    except Exception:
        pass
    return links


def crawl(
    start_url: str,
    max_depth: int,
    max_pages: int,
    timeout: float,
    delay: float,
    same_domain_only: bool,
    verify_ssl: bool,
    respect_robots: bool,
) -> Tuple[list, str]:
    session = requests.Session()
    session.headers.update({"User-Agent": DEFAULT_UA})

    # robots.txt
    rp = None
    if respect_robots:
        rp = robotparser.RobotFileParser()
        parsed = urlparse(start_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        try:
            rp.set_url(robots_url)
            rp.read()
        except Exception:
            rp = None

    q = deque()
    visited: Set[str] = set()
    results: list[PageResult] = []

    start_url = normalize_url(start_url, "") or start_url
    q.append((start_url, 0))
    visited.add(start_url)

    pages_count = 0
    start_host = start_url

    while q and pages_count < max_pages:
        url, depth = q.popleft()

        if rp is not None:
            try:
                if not rp.can_fetch(DEFAULT_UA, url):
                    pr = PageResult(
                        url=url,
                        final_url=url,
                        status=None,
                        ok=False,
                        error="Blocked by robots.txt",
                        elapsed_ms=None,
                        content_type=None,
                        redirected=False,
                        redirect_chain="",
                        depth=depth,
                        title=None,
                    )
                    results.append(pr)
                    continue
            except Exception:
                pass

        pr = fetch(session, url, timeout=timeout, verify_ssl=verify_ssl)
        pr.depth = depth
        results.append(pr)
        pages_count += 1

        if delay > 0:
            time.sleep(delay)

        if (
            pr.ok
            and pr.status
            and 200 <= pr.status < 300
            and (pr.content_type or "").lower().startswith("text/html")
            and depth < max_depth
        ):
            try:
                resp = session.get(pr.final_url, timeout=timeout, allow_redirects=True, verify=verify_ssl, stream=True)
                buf = resp.raw.read(512 * 1024, decode_content=True) 
                if not isinstance(buf, bytes):
                    buf = bytes(buf)
                new_links = extract_links(buf, pr.final_url, resp.encoding)
                for link in new_links:
                    if same_domain_only and not same_site(start_host, link):
                        continue
                    if link not in visited and len(visited) < max_pages * 5
                        visited.add(link)
                        q.append((link, depth + 1))
            except Exception:
                pass

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    csv_name = f"crawl_report_{timestamp}.csv"
    fieldnames = [
        "url",
        "final_url",
        "status",
        "ok",
        "error",
        "elapsed_ms",
        "content_type",
        "redirected",
        "redirect_chain",
        "depth",
        "title",
    ]
    with open(csv_name, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow(asdict(r))

    return results, csv_name


def main():
    parser = argparse.ArgumentParser
    parser.add_argument("--url", required=True, help="")
    parser.add_argument("--max-depth", type=int, default=0, help="")
    parser.add_argument("--max-pages", type=int, default=500, help="")
    parser.add_argument("--timeout", type=float, default=10.0, help="")
    parser.add_argument("--delay", type=float, default=0.0, help="")
    parser.add_argument("--single", action="store_true", help="")
    parser.add_argument("--allow-cross-domain", action="store_true", help="")
    parser.add_argument("--insecure", action="store_true", help="")
    parser.add_argument("--no-robots", action="store_true", help="")
    args = parser.parse_args()

    start_url = args.url.strip()
    if args.single:
        args.max_depth = 0

    same_domain_only = not args.allow_cross_domain
    verify_ssl = not args.insecure
    respect_robots = not args.no_robots

    print(f"[INFO] Start: {start_url}")
    print(f"[INFO] Depth: {args.max_depth}, Max pages: {args.max_pages}, Timeout: {args.timeout}s, Delay: {args.delay}s")
    print(f"[INFO] Same-domain only: {same_domain_only}, Verify SSL: {verify_ssl}, Respect robots.txt: {respect_robots}")

    results, csv_path = crawl(
        start_url=start_url,
        max_depth=args.max_depth,
        max_pages=args.max_pages,
        timeout=args.timeout,
        delay=args.delay,
        same_domain_only=same_domain_only,
        verify_ssl=verify_ssl,
        respect_robots=respect_robots,
    )

    total = len(results)
    errors = [r for r in results if not r.ok]
    non_2xx = [r for r in results if r.status and not (200 <= r.status < 300)]
    print("\n=== Summary ===")
    print(f"Checked: {total} page(s)")
    print(f"Non-2xx: {len(non_2xx)}")
    print(f"Errors : {len(errors)}")
    if errors[:10]:
        print("\nExamples of issues (up to 10):")
        for r in errors[:10]:
            print(f"- {r.url} | status={r.status} | error={r.error}")

    print(f"\nCSV report saved to: {csv_path}")


if __name__ == "__main__":
    main()
