import codecs

from neuro_sdk.file_filter import FileFilter, translate


async def test_empty_filter() -> None:
    ff = FileFilter()
    assert await ff.match("spam")
    assert await ff.match(".spam")
    assert await ff.match("spam/ham")


async def test_exclude_all() -> None:
    ff = FileFilter()
    ff.exclude("*")
    assert not await ff.match("spam")
    assert not await ff.match(".spam")


async def test_exclude() -> None:
    ff = FileFilter()
    ff.exclude("*.txt")
    assert await ff.match("spam")
    assert not await ff.match("spam.txt")
    assert not await ff.match(".txt")
    assert not await ff.match("dir/spam.txt")
    assert not await ff.match("dir/.txt")
    assert await ff.match("dir.txt/spam")
    assert await ff.match("dir/child.txt/spam")


async def test_exclude_include() -> None:
    ff = FileFilter()
    ff.exclude("*.txt")
    ff.include("s*")
    assert await ff.match("spam")
    assert await ff.match("spam.txt")
    assert await ff.match("ham")
    assert not await ff.match("ham.txt")
    assert not await ff.match(".txt")
    assert await ff.match("dir/spam.txt")
    assert not await ff.match("dir/ham.txt")
    assert await ff.match("dir.txt/spam")
    assert not await ff.match("dir/.txt")


async def test_exclude_with_slash() -> None:
    ff = FileFilter()
    ff.exclude("dir/*.txt")
    assert await ff.match("spam.txt")
    assert not await ff.match("dir/spam.txt")
    assert not await ff.match("dir/spam.txt/")
    assert not await ff.match("dir/.txt")
    assert await ff.match("parent/dir/spam.txt")


async def test_exclude_with_leading_slash() -> None:
    ff = FileFilter()
    ff.exclude("/spam")
    assert not await ff.match("spam")
    assert not await ff.match("spam/")
    assert await ff.match("ham")
    assert await ff.match("dir/spam")


async def test_exclude_with_trailing_slash() -> None:
    ff = FileFilter()
    ff.exclude("spam/")
    assert await ff.match("spam")
    assert not await ff.match("spam/")


async def test_exclude_crosscomponent() -> None:
    ff = FileFilter()
    ff.exclude("a?b")
    assert not await ff.match("a-b")
    assert await ff.match("a/b")

    ff = FileFilter()
    ff.exclude("a*b")
    assert not await ff.match("ab")
    assert not await ff.match("a-b")
    assert not await ff.match("arab")
    assert await ff.match("a/b")
    assert await ff.match("alice/bob")

    ff = FileFilter()
    ff.exclude("a[!0-9]b")
    assert await ff.match("a0b")
    assert not await ff.match("a-b")
    assert await ff.match("a/b")


async def test_exclude_recursive() -> None:
    ff = FileFilter()
    ff.exclude("**/dir/*.txt")
    assert await ff.match("spam.txt")
    assert not await ff.match("dir/spam.txt")
    assert await ff.match("dir/spam")
    assert not await ff.match("parent/dir/spam.txt")
    assert await ff.match("parent/dir/spam")

    ff = FileFilter()
    ff.exclude("dir/**/*.txt")
    assert await ff.match("spam.txt")
    assert not await ff.match("dir/spam.txt")
    assert await ff.match("dir/spam")
    assert not await ff.match("dir/child/spam.txt")
    assert await ff.match("dir/child/spam")

    ff = FileFilter()
    ff.exclude("dir/**")
    assert await ff.match("spam")
    assert not await ff.match("dir/")
    assert await ff.match("dir")
    assert not await ff.match("dir/child")
    assert not await ff.match("dir/child/")
    assert not await ff.match("dir/child/spam")

    ff = FileFilter()
    ff.exclude("dir/**/")
    assert await ff.match("spam")
    assert not await ff.match("dir/")
    assert await ff.match("dir")
    assert not await ff.match("dir/child/")
    assert await ff.match("dir/child")
    assert not await ff.match("dir/child/")
    assert not await ff.match("dir/child/spam/")
    assert await ff.match("dir/child/spam")


async def test_exclude_include_with_prefix() -> None:
    ff = FileFilter()
    ff.exclude("*.txt", "parent/")
    ff.include("s*", "parent/child/")

    assert await ff.match("spam.txt")
    assert await ff.match("ham.txt")
    assert not await ff.match("parent/spam.txt")
    assert not await ff.match("parent/ham.txt")
    assert await ff.match("other/spam.txt")
    assert await ff.match("other/ham.txt")
    assert await ff.match("parent/child/spam.txt")
    assert not await ff.match("parent/child/ham.txt")


def test_translate() -> None:
    assert translate("") == "/?"
    assert translate("abc") == r"abc/?"
    assert translate("/abc") == r"/abc/?"
    assert translate("abc/") == r"abc/"
    assert translate("abc/de") == r"abc/de/?"
    assert translate("a?c") == r"a[^/]c/?"
    assert translate("a*c") == r"a[^/]*c/?"
    assert translate("a[bc]d") == r"a[bc](?<!/)d/?"
    assert translate("a[b-d]e") == r"a[b-d](?<!/)e/?"
    assert translate("a[!b-d]e") == r"a[^b-d](?<!/)e/?"
    assert translate("[a-zA-Z_]") == r"[a-zA-Z_](?<!/)/?"
    assert translate(r"\?") == r"\?/?"


def test_translate_recursive() -> None:
    assert translate("**") == r".*"
    assert translate("**/") == r"(?:.+/)?"
    assert translate("**/abc") == r"(?:.+/)?abc/?"
    assert translate("/**") == r"/.*"
    assert translate("abc/**") == r"abc/.*"
    assert translate("/**/") == r"/(?:.+/)?"
    assert translate("abc/**/def") == r"abc/(?:.+/)?def/?"


async def test_read_from_buffer() -> None:
    ff = FileFilter()
    ff.read_from_buffer(
        codecs.BOM_UTF8 + b"*.txt  \r\n"  # CRLF and trailing spaces
        b"\n"  # empty line
        b"# comment\n"  # comment
        b"!s*",  # negation
        prefix="base/",
    )
    assert len(ff.filters) == 2
    assert await ff.match("base/spam.txt")
    assert not await ff.match("base/ham.txt")
    assert await ff.match("ham.txt")


async def test_parent_ignore_file() -> None:
    ff = FileFilter()
    ff.exclude("dir/s*", "", "dir/")
    ff.exclude("/*.txt", "", "dir/")
    assert not await ff.match("spam.txt")
    assert await ff.match("ham.txt")
    assert not await ff.match("spam")
