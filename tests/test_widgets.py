from app.ui.widgets import countdown_text


def test_countdown_text():
    assert countdown_text(42) == "42"
    assert countdown_text(41.2) == "42"  # arredonda para cima: só mostra 0 quando acabou
    assert countdown_text(0.3) == "1"
    assert countdown_text(0) == "0"
    assert countdown_text(-1) == "0"
    assert countdown_text(60) == "1:00"
    assert countdown_text(65) == "1:05"


def test_render_ring_shrinks_from_full_to_empty():
    from app.ui.widgets import render_ring

    color, bg = "#00a3a6", "#ebebeb"
    teal, gray = (0, 163, 166), (235, 235, 235)

    def at(img, x, y):
        return img.getpixel((x, y))

    empty = render_ring(100, 10, 0, color, bg)
    assert empty.size == (100, 100) and empty.getcolors() == [(100 * 100, gray)]

    full = render_ring(100, 10, 1, color, bg)
    for x, y in [(50, 6), (94, 50), (50, 94), (6, 50)]:  # topo, direita, baixo, esquerda
        assert at(full, x, y) == teal

    quarter = render_ring(100, 10, 0.25, color, bg)  # do topo até as 3h, no sentido horário
    assert at(quarter, 80, 20) == teal
    assert at(quarter, 50, 94) == gray and at(quarter, 6, 50) == gray
