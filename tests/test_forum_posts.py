"""Три форумных эндпоинта, ради которых мок перестал отвечать пустотой.

Каждый тест назван тем, что сломается без него, а не тем, что он вызывает: до этих ручек
`posts_list` и `posts_likes` уходили в catch-all, который на `Passthrough` отвечает `{}` со
статусом 200 — и сценарий, читающий участников темы, завершался зелёным, не увидев никого.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from lzt_testnet.api.app import create_app

_AUTH = {"Authorization": "Bearer testnet"}
_THREAD = 7


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _seed(client: TestClient, user_id: int, body: str = "участвую") -> int:
    response = client.post(
        "/testnet/forum/seed-post",
        json={"thread_id": _THREAD, "poster_user_id": user_id, "post_body": body},
        headers=_AUTH,
    )
    assert response.status_code == 200
    return int(response.json()["post_id"])


def test_a_thread_returns_the_people_who_posted(client: TestClient) -> None:
    """Главное: список участников — настоящий, а не пустой объект от catch-all."""
    _seed(client, 100)
    _seed(client, 200)

    payload = client.get("/posts", params={"thread_id": _THREAD}, headers=_AUTH).json()

    assert [p["poster_user_id"] for p in payload["posts"]] == [100, 200]


def test_the_same_person_posting_twice_stays_twice(client: TestClient) -> None:
    """Мок НЕ дедуплицирует. Дедупликация — работа узла раздачи, и она главное, что в нём может
    сломаться; стенд, схлопывающий дубли за него, скрыл бы ровно тот дефект, ради которого нужен."""
    _seed(client, 100, "первое")
    _seed(client, 100, "второе")

    payload = client.get("/posts", params={"thread_id": _THREAD}, headers=_AUTH).json()

    assert [p["poster_user_id"] for p in payload["posts"]] == [100, 100]


def test_the_total_is_the_whole_thread_not_the_page(client: TestClient) -> None:
    """Читающий решает по `posts_total`, брать ли следующую страницу. Считай он по длине страницы —
    остановился бы на последней короткой и выкинул тех, кто написал последним."""
    for user_id in range(1, 6):
        _seed(client, user_id)

    payload = client.get(
        "/posts", params={"thread_id": _THREAD, "page": 1, "limit": 2}, headers=_AUTH
    ).json()

    assert len(payload["posts"]) == 2
    assert payload["posts_total"] == 5


def test_pages_do_not_overlap_or_skip(client: TestClient) -> None:
    for user_id in range(1, 6):
        _seed(client, user_id)

    seen: list[int] = []
    for page in (1, 2, 3):
        payload = client.get(
            "/posts", params={"thread_id": _THREAD, "page": page, "limit": 2}, headers=_AUTH
        ).json()
        seen.extend(p["poster_user_id"] for p in payload["posts"])

    assert seen == [1, 2, 3, 4, 5]


def test_a_request_without_a_thread_id_still_answers(client: TestClient) -> None:
    """Без `thread_id` — пустая тема и 200.

    Сначала было 404: «потерянный `thread_id` — не то же самое, что пустая тема», и по смыслу это
    верно. Но апстрим объявляет параметр необязательным, а смоук стенда (`test_all_methods_e2e`)
    требует 200 от КАЖДОГО метода на голый запрос — ломать общий контракт ради одной ручки дороже,
    чем ловить потерянный идентификатор там, где он теряется.
    """
    response = client.get("/posts", headers=_AUTH)

    assert response.status_code == 200
    assert response.json()["posts"] == []


def test_a_published_post_is_readable_back(client: TestClient) -> None:
    """То, на чём стоит вся раздача: она публикует коммитмент, ждёт и читает тему обратно."""
    created = client.post(
        "/posts", json={"post_body": "хэш зерна: abc", "thread_id": _THREAD}, headers=_AUTH
    ).json()

    payload = client.get("/posts", params={"thread_id": _THREAD}, headers=_AUTH).json()

    assert created["post"]["post_id"] in [p["post_id"] for p in payload["posts"]]
    assert payload["posts"][0]["post_body"] == "хэш зерна: abc"


def test_likes_come_back_under_the_key_the_spec_names(client: TestClient) -> None:
    """`users`, а не `likes`: имя ключа взято из спеки, и по нему клиент разбирает ответ."""
    post_id = _seed(client, 100)
    client.post(
        "/testnet/forum/seed-like", json={"post_id": post_id, "user_id": 300}, headers=_AUTH
    )

    payload = client.get(f"/posts/{post_id}/likes", headers=_AUTH).json()

    assert [u["user_id"] for u in payload["users"]] == [300]


def test_one_person_likes_once(client: TestClient) -> None:
    """Повтор не удваивает симпатию — иначе стенд прятал бы двойной подсчёт участника."""
    post_id = _seed(client, 100)
    for _ in range(2):
        client.post(
            "/testnet/forum/seed-like", json={"post_id": post_id, "user_id": 300}, headers=_AUTH
        )

    payload = client.get(f"/posts/{post_id}/likes", headers=_AUTH).json()

    assert len(payload["users"]) == 1


def test_reset_clears_the_forum_too(client: TestClient) -> None:
    """Иначе тема протекает между сценариями, и второй прогон стартует с чужими участниками."""
    _seed(client, 100)
    client.post("/testnet/reset", headers=_AUTH)

    payload = client.get("/posts", params={"thread_id": _THREAD}, headers=_AUTH).json()

    assert payload["posts"] == []


def test_every_json_response_carries_system_info(client: TestClient) -> None:
    """Конверт ставит middleware, поэтому ни одна ручка не может его забыть — включая те, что
    напишут после этого файла."""
    for response in (
        client.get("/posts", params={"thread_id": _THREAD}, headers=_AUTH),
        client.get("/posts/1/likes", headers=_AUTH),
        client.post("/posts", json={"post_body": "x", "thread_id": _THREAD}, headers=_AUTH),
    ):
        assert set(response.json()["system_info"]) == {"visitor_id", "time", "log_id"}


def test_an_error_does_not_get_a_success_envelope(client: TestClient) -> None:
    """Форма ошибки — её собственный контракт. Приклеив к ней `system_info`, middleware заставил бы
    клиента, который ветвится по форме ответа, принять отказ за успех."""
    # Путь из НЕСКОЛЬКИХ сегментов: односегментный проглатывает `GetLot`, объявленный апстримом
    # как `/{item_id}` — он матчит что угодно и отвечает 200. Свойство чужого каталога, не стенда.
    response = client.get("/zzz/yyy/xxx", headers=_AUTH)

    assert response.status_code == 404
    assert "system_info" not in response.json()
