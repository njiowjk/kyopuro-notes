"""Update managed lists of approved solution notes in domain indexes."""

from collections import defaultdict
import os
from pathlib import Path
import re
from unicodedata import normalize
from urllib.parse import quote, unquote, urlsplit


BEGIN = "<!-- BEGIN AUTO: domain-solutions -->"
END = "<!-- END AUTO: domain-solutions -->"
LINK = r"\[((?:\\.|[^\]\\])+)\]\(([^()\r\n]+)\)"
PROPOSALS = Path("管理") / "追加候補.md"


class DomainLinkError(Exception):
    """A malformed proposal or managed region that requires editing."""


def markdown_lines(path, lines):
    """Yield the indices and contents of lines outside fenced examples."""
    fence = None
    for index, line in enumerate(lines):
        match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line.rstrip("\r\n"))
        if fence is None:
            if match:
                fence = match[1]
            else:
                yield index, line
        elif match and match[1].startswith(fence) and not match[2].strip():
            fence = None
    if fence is not None:
        raise DomainLinkError(f"{path.name}のコードブロックが閉じられていません。")


def markdown_target(origin, destination):
    try:
        url = urlsplit(destination)
    except ValueError:
        return None
    path = unquote(url.path)
    if (
        not url.scheme and not url.netloc and not Path(path).is_absolute()
        and "\0" not in path and path.endswith(".md")
    ):
        return Path(os.path.abspath(origin.parent / path))
    return None


def approved_notes(vault, proposals, content):
    visible = "".join(line for _, line in markdown_lines(proposals, content.splitlines(keepends=True)))
    groups = defaultdict(dict)
    for section in re.split(r"(?m)^## ", visible)[1:]:
        states = [state.strip() for state in re.findall(r"(?m)^- 状態[ \t　]+([^\r\n]+)", section)]
        if "作成済み" not in states:
            continue
        paths = re.findall(r"(?m)^- 主分野・保存先[ \t　]+([^\r\n]+)", section)
        match = re.fullmatch(LINK, paths[0].strip()) if len(paths) == 1 else None
        title = section.splitlines()[0]
        if states != ["作成済み"] or not match:
            raise DomainLinkError(f"作成済み候補「{title}」の状態または保存先の形式を確認してください。")
        label, link = match.groups()
        label = re.sub(r"\\([\\\[\]])", r"\1", label)
        target = markdown_target(proposals, link)
        if (
            target is None or target.parent.parent != vault / "分野"
            or target.stem == target.parent.name
            or target.resolve() != target or not target.is_file()
        ):
            raise DomainLinkError(f"作成済み候補「{title}」の保存先が分野内の解法ノートではありません。")
        if label.startswith("分野/") and normalize("NFC", unquote(label)) != normalize(
            "NFC", target.relative_to(vault).as_posix()
        ):
            raise DomainLinkError(f"作成済み候補「{title}」の表示上の保存先とリンク先が一致しません。")
        group = groups[normalize("NFC", target.parent.name)]
        group.setdefault(normalize("NFC", target.name), target.name)
    return groups


def render_domain_index(vault, index, original, names):
    lines = original.splitlines(keepends=True)
    visible = dict(markdown_lines(index, lines))
    starts = [i for i, line in visible.items() if line.rstrip("\r\n") == BEGIN]
    ends = [i for i, line in visible.items() if line.rstrip("\r\n") == END]
    if not starts and not ends:
        return None
    if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
        raise DomainLinkError(f"{index.name}の domain-solutions マーカーを確認してください。")
    start, end = starts[0], ends[0]
    for line in lines[start + 1:end]:
        if not line.strip():
            continue
        match = re.fullmatch("- " + LINK, line.rstrip("\r\n"))
        target = markdown_target(index, match[2]) if match else None
        if target is None or target.parent != index.parent or target == index:
            raise DomainLinkError(f"{index.name}の domain-solutions 内に一覧以外の内容があります。")

    manual = set()
    for i, line in visible.items():
        if start <= i <= end:
            continue
        for _, link in re.findall(LINK, line):
            target = markdown_target(index, link)
            if target is not None:
                target = target.resolve()
                if target.parent == index.parent:
                    manual.add(normalize("NFC", target.name))
        for link in re.findall(r"\[\[([^]|#\n]+)(?:[|#][^]\n]*)?\]\]", line):
            path = Path(link)
            if not path.is_absolute() and (
                path.parent == Path(".") or (vault / path).parent == index.parent
            ):
                name = path.name if path.suffix == ".md" else path.name + ".md"
                manual.add(normalize("NFC", name))

    newline = "\r\n" if lines[start].endswith("\r\n") else "\n"
    items = []
    for key in sorted(names.keys() - manual):
        name = names[key]
        title = re.sub(r"([\\\[\]])", r"\\\1", name.removesuffix(".md"))
        link = "".join(quote(c, safe="") if c.isascii() or c.isspace() else c for c in name)
        items.append(f"- [{title}]({link}){newline}")
    body = newline + "".join(items) + (newline if items else "")
    return "".join(lines[:start + 1]) + body + "".join(lines[end:])


def plan_domain_links(vault, proposals, content):
    groups = approved_notes(vault, proposals, content.decode("utf-8"))
    updates = []
    managed = set()
    for folder in sorted((vault / "分野").glob("*/")):
        index = folder / f"{folder.name}.md"
        if not index.is_file() or index.resolve() != index:
            continue
        original = index.read_bytes()
        domain = normalize("NFC", index.parent.name)
        updated = render_domain_index(vault, index, original.decode("utf-8"), groups.get(domain, {}))
        if updated is None:
            continue
        managed.add(domain)
        encoded = updated.encode("utf-8")
        if encoded != original:
            updates.append((index, original, encoded))
    return updates, sorted(groups.keys() - managed)
