from app.core.templates import build_variables, html_to_text, render, unknown_variables


def vars_():
    return build_variables(
        {"Nome": "Ana Lima", "Data do Curso": "03/11/2026", "Curso": "R&D <básico>"},
        name="Ana Lima",
        email="ana@x.com",
        filename="ana.pdf",
    )


def test_render_basic_and_column_variables():
    v = vars_()
    out = render("Olá {nome} ({primeiro_nome}), curso {Curso} em {data_do_curso} / {Data do Curso}. {x}", v)
    assert out == "Olá Ana Lima (Ana), curso R&D <básico> em 03/11/2026 / 03/11/2026. {x}"


def test_render_html_escapes_values():
    assert render("<b>{curso}</b>", vars_(), escape_html=True) == "<b>R&amp;D &lt;básico&gt;</b>"


def test_unknown_variables():
    assert unknown_variables("{nome} {foo} {Foo} {bar}", vars_()) == ["{foo}", "{Foo}", "{bar}"]


def test_html_to_text():
    html = """<html><head><style>p{color:red}</style></head><body>
    <h2>Título</h2><p>Olá, <strong>Ana</strong>!</p><p>Linha 1<br>Linha 2</p>
    <ul><li>Um</li><li>Dois</li></ul><a href="https://site.com">site</a></body></html>"""
    text = html_to_text(html)
    assert "color" not in text
    assert "Título" in text and "Olá, Ana!" in text
    assert "Linha 1\nLinha 2" in text
    assert "- Um" in text and "- Dois" in text
    assert "site (https://site.com)" in text


def test_format_person_name():
    from app.core.text import format_person_name

    assert format_person_name("ANA-LUÍSA D'ÁVILA E SILVA") == "Ana-Luísa D'Ávila e Silva"
    assert format_person_name("PEDRO II") == "Pedro II"
    assert format_person_name("  JOSÉ   SOUZA ") == "José Souza"
    assert format_person_name("DiCaprio") == "DiCaprio"
    assert format_person_name("") == ""
