"""Read task links from AtCoder submission pages."""

from html.parser import HTMLParser
from http.client import HTTPException
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


ATCODER_ID = r"[A-Za-z0-9][A-Za-z0-9_-]*"
ATCODER_PATH = re.compile(
    rf"/contests/(?P<contest_id>{ATCODER_ID})/"
    rf"(?:submissions/(?P<submission_id>[0-9]+)|tasks/(?P<task_id>{ATCODER_ID}))/?"
)

MAX_HTML_BYTES = 4 * 1024 * 1024
TIMEOUT_SECONDS = 8


class InvalidURL(ValueError):
    """An invalid or unsupported AtCoder URL."""


class ResolutionError(Exception):
    def __init__(self, code, *, blocked=False):
        super().__init__(code)
        self.code = code
        self.blocked = blocked


def parse_url(value):
    if not isinstance(value, str):
        raise InvalidURL("URLは文字列で指定してください。")
    url = value.strip()
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in url):
        raise InvalidURL("URLの途中に空白または制御文字があります。")
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
    except ValueError as error:
        raise InvalidURL("URLの形式が正しくありません。") from error
    if parsed.scheme != "https" or hostname != "atcoder.jp":
        raise InvalidURL("atcoder.jp のHTTPS URLを指定してください。")
    if parsed.username is not None or parsed.password is not None:
        raise InvalidURL("ユーザー情報を含むURLは登録できません。")
    if parsed.netloc.lower() not in ("atcoder.jp", "atcoder.jp:443"):
        raise InvalidURL("ポートを指定する場合は443を使ってください。")

    match = ATCODER_PATH.fullmatch(parsed.path)
    if match is None:
        raise InvalidURL("AtCoderの提出URL（提出IDは数字）か問題URLを指定してください。")
    ids = match.groupdict()
    return {
        "kind": "submission" if ids["submission_id"] is not None else "problem",
        "url": "https://atcoder.jp" + parsed.path.removesuffix("/"),
        **ids,
    }


class SubmissionLinks(HTMLParser):
    """Collect links from data cells in labelled table rows."""

    ignored = {"nav", "footer", "aside", "template", "pre", "code", "textarea"}
    tracked = ignored | {"table", "tr", "th", "td"}

    def __init__(self):
        super().__init__()
        self.stack = []
        self.row_links = []
        self.has_header = False
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag in self.tracked:
            self.stack.append(tag)
        if self.ignored.intersection(self.stack):
            return
        if tag == "tr":
            self.row_links = []
            self.has_header = False
        elif tag == "th" and "tr" in self.stack:
            self.has_header = True
        elif tag == "a" and self.stack[-2:] == ["tr", "td"] and "table" in self.stack:
            href = dict(attrs).get("href")
            if href:
                self.row_links.append(href)

    def handle_endtag(self, tag):
        if tag not in self.stack:
            return
        if tag == "tr" and self.has_header and not self.ignored.intersection(self.stack):
            self.links.extend(self.row_links)
        index = len(self.stack) - 1 - self.stack[::-1].index(tag)
        del self.stack[index:]


def extract_task(html, submission_url):
    parser = SubmissionLinks()
    try:
        parser.feed(html)
        parser.close()
    except AssertionError:
        raise ResolutionError("unexpected_page") from None
    candidates = {}
    for href in parser.links:
        try:
            target = parse_url(urljoin(submission_url, href))
        except ValueError:
            continue
        if target["kind"] == "problem":
            candidates[target["url"]] = target
    if not candidates:
        raise ResolutionError("missing_task_link")
    if len(candidates) > 1:
        raise ResolutionError("ambiguous_task_link", blocked=True)
    return next(iter(candidates.values()))


def check_submission_url(expected, actual):
    try:
        parsed = parse_url(actual)
    except InvalidURL:
        # A same-origin redirect to /login, for example, may be temporary.
        try:
            parts = urlsplit(actual)
        except ValueError:
            parts = None
        same_origin = parts is not None and parts.scheme == "https" and parts.netloc.lower() in (
            "atcoder.jp", "atcoder.jp:443"
        )
        if same_origin:
            raise ResolutionError("unexpected_page") from None
        raise ResolutionError("unsafe_redirect", blocked=True) from None
    if parsed["url"] != expected:
        raise ResolutionError("unexpected_page", blocked=True)


class SubmissionRedirectHandler(HTTPRedirectHandler):
    max_redirections = 2
    max_repeats = 1

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            check_submission_url(parse_url(req.full_url)["url"], newurl)
        except ResolutionError:
            fp.close()
            raise
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        cookie = req.unredirected_hdrs.get("Cookie")
        if redirected is not None and cookie is not None:
            redirected.add_unredirected_header("Cookie", cookie)
        return redirected

    # Validate Location before urllib's own parsing or redirect-scheme checks.
    def http_error_302(self, req, fp, code, msg, headers):
        location = headers.get("location") or headers.get("uri")
        if location:
            try:
                target = urljoin(req.full_url, location)
            except ValueError:
                fp.close()
                raise ResolutionError("unsafe_redirect", blocked=True) from None
            try:
                check_submission_url(parse_url(req.full_url)["url"], target)
            except ResolutionError:
                fp.close()
                raise
        return super().http_error_302(req, fp, code, msg, headers)

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302


def fetch_task(submission_url, *, session=None):
    submission = parse_url(submission_url)
    if submission["kind"] != "submission":
        raise InvalidURL("提出URLを指定してください。")
    url = submission["url"]
    opener = build_opener(ProxyHandler({}), SubmissionRedirectHandler())
    request = Request(url, headers={"User-Agent": "kyopuro-notes/1.0", "Accept": "text/html"})
    if session is not None and session.header is not None:
        request.add_unredirected_header("Cookie", session.header)
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            check_submission_url(url, response.geturl())
            if response.status != 200 or response.headers.get_content_type() != "text/html":
                raise ResolutionError("unexpected_page")
            html = response.read(MAX_HTML_BYTES + 1)
    except HTTPError as error:
        error.close()
        failure = f"http_{error.code}"
    except TimeoutError:
        failure = "timeout"
    except URLError as error:
        failure = "timeout" if isinstance(error.reason, TimeoutError) else "network"
    except (OSError, HTTPException, ValueError):
        failure = "network"
    else:
        if len(html) > MAX_HTML_BYTES:
            raise ResolutionError("html_too_large")
        return extract_task(html.decode("utf-8", errors="replace"), url)
    # Keep raw HTTP errors and their response headers out of the exception chain.
    raise ResolutionError(failure)
