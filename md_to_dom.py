from mistletoe import Document, block_token, span_token
from mistletoe.base_renderer import BaseRenderer


class TelegraphDomRenderer(BaseRenderer):
    """
    Convert a mistletoe AST into Telegraph DOM nodes.
    """

    def render_document(self, token: block_token.Document):
        nodes = []
        for child in token.children:
            rendered = self.render(child)
            if rendered is None:
                continue
            nodes.append(rendered)
        return nodes

    def render_paragraph(self, token: block_token.Paragraph):
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

    def render_heading(self, token: block_token.Heading):
        if token.level == 1:
            return {"tag": "h3", "children": self.render_inner(token)}
        if token.level == 2:
            return {"tag": "h4", "children": self.render_inner(token)}
        return {
            "tag": "p",
            "children": [{"tag": "strong", "children": self.render_inner(token)}],
        }

    def render_list(self, token: block_token.List):
        tag = "ol" if token.start is not None else "ul"
        return {
            "tag": tag,
            "children": [self.render(child) for child in token.children],
        }

    def render_list_item(self, token: block_token.ListItem):
        return {"tag": "li", "children": self.render_inner(token)}

    def render_strong(self, token: span_token.Strong):
        return {"tag": "strong", "children": self.render_inner(token)}

    def render_emphasis(self, token: span_token.Emphasis):
        return {"tag": "em", "children": self.render_inner(token)}

    def render_inline_code(self, token: span_token.InlineCode):
        if token.children:
            return {"tag": "code", "children": [token.children[0].content]}
        return {"tag": "code", "children": [token.content]}

    def render_strikethrough(self, token: span_token.Strikethrough):
        return {"tag": "del", "children": self.render_inner(token)}

    def render_image(self, token: span_token.Image):
        attrs = {"src": token.src}
        alt_text = self.render_inner(token)
        if alt_text:
            attrs["alt"] = alt_text
        if token.title:
            attrs["title"] = token.title
        return {"tag": "img", "attrs": attrs}

    def render_link(self, token: span_token.Link):
        attrs = {"href": token.target}
        if token.title:
            attrs["title"] = token.title
        return {"tag": "a", "attrs": attrs, "children": self.render_inner(token)}

    def render_auto_link(self, token: span_token.AutoLink):
        return {"tag": "a", "attrs": {"href": token.target}, "children": [token.target]}

    def render_raw_text(self, token: span_token.RawText):
        return token.content

    def render_line_break(self, token: span_token.LineBreak):
        if token.soft:
            return " "
        return {"tag": "br"}

    def render_block_code(self, token: block_token.BlockCode):
        code_dict = {
            "tag": "code",
            "children": self.code_children_from_text(token.content),
        }
        if token.language:
            code_dict.setdefault("attrs", {})["class"] = "language-" + token.language
        return {"tag": "pre", "children": [code_dict]}

    def render_quote(self, token: block_token.Quote):
        return {"tag": "blockquote", "children": self.render_inner(token)}

    def render_thematic_break(self, token: block_token.ThematicBreak):
        return {"tag": "hr"}

    def render_html_block(self, token: block_token.HTMLBlock):
        return token.content

    def render_html_span(self, token: span_token.HTMLSpan):
        return token.content

    def render_inner(self, token):
        result = []
        for child in token.children:
            rendered = self.render(child)
            if rendered is None:
                continue
            if isinstance(rendered, list):
                result.extend([r for r in rendered if r not in ("", " ")])
            else:
                if rendered not in ("", " "):
                    result.append(rendered)
        return result

    def code_children_from_text(self, text: str):
        lines = text.rstrip("\n").split("\n")
        children = []
        for idx, line in enumerate(lines):
            children.append(line)
            if idx != len(lines) - 1:
                children.append({"tag": "br"})
        return children


def md_to_dom(markdown_text: str):
    with TelegraphDomRenderer() as renderer:
        return renderer.render(Document(markdown_text))
