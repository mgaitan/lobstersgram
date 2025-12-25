from mistletoe import Document, block_token, span_token
from mistletoe.base_renderer import BaseRenderer

type Node = dict[str, object] | str
type NodeList = list[Node]

HEADING_LEVEL_PRIMARY = 1
HEADING_LEVEL_SECONDARY = 2


class TelegraphDomRenderer(BaseRenderer):
    """
    Convert a mistletoe AST into Telegraph DOM nodes.
    """

    def render_document(self, token: block_token.Document) -> NodeList:
        nodes: NodeList = []
        for child in token.children:
            rendered = self.render(child)
            if rendered is None:
                continue
            nodes.append(rendered)
        return nodes

    def render_paragraph(self, token: block_token.Paragraph) -> dict[str, object] | None:
        children = self.render_inner(token)
        children = [c for c in children if c not in ("", " ")]
        if not children:
            return None
        if (
            len(children) == 1
            and isinstance(children[0], dict)
            and children[0].get("tag") == "code"
            and "\n" in "".join(children[0].get("children", []))
        ):
            code_text = "".join(children[0].get("children", []))
            children[0]["children"] = self.code_children_from_text(code_text)
            return {"tag": "pre", "children": children}
        return {"tag": "p", "children": children}

    def render_heading(self, token: block_token.Heading) -> dict[str, object]:
        if token.level == HEADING_LEVEL_PRIMARY:
            return {"tag": "h3", "children": self.render_inner(token)}
        if token.level == HEADING_LEVEL_SECONDARY:
            return {"tag": "h4", "children": self.render_inner(token)}
        return {
            "tag": "p",
            "children": [{"tag": "strong", "children": self.render_inner(token)}],
        }

    def render_list(self, token: block_token.List) -> dict[str, object]:
        tag = "ol" if token.start is not None else "ul"
        return {
            "tag": tag,
            "children": [self.render(child) for child in token.children],
        }

    def render_list_item(self, token: block_token.ListItem) -> dict[str, object]:
        return {"tag": "li", "children": self.render_inner(token)}

    def render_strong(self, token: span_token.Strong) -> dict[str, object]:
        return {"tag": "strong", "children": self.render_inner(token)}

    def render_emphasis(self, token: span_token.Emphasis) -> dict[str, object]:
        return {"tag": "em", "children": self.render_inner(token)}

    def render_inline_code(self, token: span_token.InlineCode) -> dict[str, object]:
        if token.children:
            return {"tag": "code", "children": [token.children[0].content]}
        return {"tag": "code", "children": [token.content]}

    def render_strikethrough(self, token: span_token.Strikethrough) -> dict[str, object]:
        return {"tag": "del", "children": self.render_inner(token)}

    def render_image(self, token: span_token.Image) -> dict[str, object]:
        attrs = {"src": token.src}
        alt_text = self.render_inner(token)
        if alt_text:
            attrs["alt"] = alt_text
        if token.title:
            attrs["title"] = token.title
        return {"tag": "img", "attrs": attrs}

    def render_link(self, token: span_token.Link) -> dict[str, object]:
        attrs = {"href": token.target}
        if token.title:
            attrs["title"] = token.title
        return {"tag": "a", "attrs": attrs, "children": self.render_inner(token)}

    def render_auto_link(self, token: span_token.AutoLink) -> dict[str, object]:
        return {"tag": "a", "attrs": {"href": token.target}, "children": [token.target]}

    def render_raw_text(self, token: span_token.RawText) -> str:
        return token.content

    def render_line_break(self, token: span_token.LineBreak) -> dict[str, object] | str:
        if token.soft:
            return " "
        return {"tag": "br"}

    def render_block_code(self, token: block_token.BlockCode) -> dict[str, object]:
        code_dict = {
            "tag": "code",
            "children": self.code_children_from_text(token.content),
        }
        if token.language:
            code_dict.setdefault("attrs", {})["class"] = "language-" + token.language
        return {"tag": "pre", "children": [code_dict]}

    def render_quote(self, token: block_token.Quote) -> dict[str, object]:
        return {"tag": "blockquote", "children": self.render_inner(token)}

    def render_thematic_break(self, token: block_token.ThematicBreak) -> dict[str, object]:
        return {"tag": "hr"}

    def render_html_block(self, token: block_token.HTMLBlock) -> str:
        return token.content

    def render_html_span(self, token: span_token.HTMLSpan) -> str:
        return token.content

    def render_inner(self, token: object) -> NodeList:
        result: NodeList = []
        for child in token.children:
            rendered = self.render(child)
            if rendered is None:
                continue
            if isinstance(rendered, list):
                result.extend([r for r in rendered if r not in ("", " ")])
            elif rendered not in ("", " "):
                result.append(rendered)
        return result

    def code_children_from_text(self, text: str) -> NodeList:
        lines = text.rstrip("\n").split("\n")
        children: NodeList = []
        for idx, line in enumerate(lines):
            children.append(line)
            if idx != len(lines) - 1:
                children.append({"tag": "br"})
        return children


def md_to_dom(markdown_text: str) -> NodeList:
    with TelegraphDomRenderer() as renderer:
        return renderer.render(Document(markdown_text))
