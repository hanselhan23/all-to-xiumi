import base64
import hashlib
import io

import pytest
pytest.importorskip("premailer")
pytest.importorskip("PIL")
from lxml import html
from PIL import Image

from all_to_xiumi.skill_pipeline import run_skill
from all_to_xiumi.wechat_copy import prepare_wechat_copy


def image_bytes(format="PNG", animated=False):
    output = io.BytesIO()
    first = Image.new("RGB", (12, 8), "purple")
    if animated:
        first.save(output, format=format, save_all=True,
                   append_images=[Image.new("RGB", (12, 8), "orange")], duration=80, loop=0)
    else:
        first.save(output, format=format)
    return output.getvalue()


def test_styles_and_both_media_types_survive_preparation(tmp_path):
    png, gif = image_bytes(), image_bytes("GIF", True)
    (tmp_path / "照片.png").write_bytes(png)
    (tmp_path / "run.gif").write_bytes(gif)
    source = '<html><head><style>.box{color:#8020cc;padding:10px;width:50%}</style></head><body><article><section class="box" style="color:#123456"><p>正文 <strong>粗体</strong></p><img src="照片.png"><img src="run.gif"></section></article></body></html>'
    page, report = prepare_wechat_copy(source, base_dir=tmp_path)
    article = html.fromstring(page).get_element_by_id("gzh-content")
    style = article.cssselect(".box")[0].get("style")
    assert "color:#123456" in style.replace(" ", "")
    assert "width:50%" in style.replace(" ", "")
    assert "padding:10px" in style.replace(" ", "")
    assert not article.cssselect("style,script,button")
    decoded = [base64.b64decode(node.get("src").split(",", 1)[1]) for node in article.cssselect("img")]
    assert decoded == [png, gif]
    assert report["assets"][1]["frames"] == 2
    assert [item["sha256"] for item in report["assets"]] == [hashlib.sha256(item).hexdigest() for item in (png, gif)]


def test_body_style_and_css_background_are_portable(tmp_path):
    png = image_bytes()
    (tmp_path / "background.png").write_bytes(png)
    page, report = prepare_wechat_copy('<body style="font-size:19px;color:#306;background-image:url(background.png)"><p>有背景的正文</p></body>', base_dir=tmp_path)
    article = html.fromstring(page).get_element_by_id("wechat-article")
    assert "font-size:19px" in article.get("style").replace(" ", "")
    assert "data:image/png;base64," in article.get("style")
    assert report["assets"][0]["sha256"] == hashlib.sha256(png).hexdigest()


@pytest.mark.parametrize("source", [
    "<article><video src='a.mp4'></video></article>",
    "<article><svg><path d='M0 0L10 10'/></svg></article>",
    "<article><script>document.write('内容')</script></article>",
    "<style>@media(max-width:500px){p{font-size:20px}}</style><article><p>响应式文字</p></article>",
])
def test_incompatible_content_is_not_silently_discarded(source, tmp_path):
    with pytest.raises(ValueError):
        prepare_wechat_copy(source, base_dir=tmp_path)


def test_copy_mode_bypasses_xiumi_and_keeps_the_original(tmp_path, monkeypatch):
    from all_to_xiumi import skill_pipeline

    def forbidden_publish(*args, **kwargs):
        pytest.fail("直接复制路径不应调用秀米")

    monkeypatch.setattr(skill_pipeline, "publish_xiumi_draft", forbidden_publish)
    source = tmp_path / "input.html"
    original = '<article style="font-size:17px"><p>验证原稿不被覆盖</p></article>'
    source.write_text(original, encoding="utf-8")
    target = tmp_path / "copy.html"
    result = run_skill(str(source), wechat_copy=True, output_path=str(target))
    assert result["status"] == "wechat_copy_ready"
    assert result["draft_url"] == ""
    assert "复制到公众号" in target.read_text(encoding="utf-8")
    assert source.read_text(encoding="utf-8") == original
    with pytest.raises(ValueError, match="覆盖原稿"):
        run_skill(str(source), wechat_copy=True, output_path=str(source))


def test_markdown_local_images_resolve_against_the_input_directory(tmp_path):
    image = image_bytes()
    (tmp_path / "photo.png").write_bytes(image)
    source = tmp_path / "note.md"
    source.write_text("# 标题\n\n![图片](photo.png)\n\n正文 **重点**", encoding="utf-8")
    target = tmp_path / "ready" / "article.html"
    result = run_skill(str(source), template="generic", wechat_copy=True, output_path=str(target), output_dir=str(tmp_path / "unused"))
    assert result["copy_report"]["images"] == 1
    assert result["copy_report"]["assets"][0]["sha256"] == hashlib.sha256(image).hexdigest()
    assert list((tmp_path / "unused").glob("*.html")) == []
