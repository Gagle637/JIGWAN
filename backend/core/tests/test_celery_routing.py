from django.conf import settings

from config.celery import app as celery_app


def test_routed_task_resolves_to_its_declared_queue():
    options = celery_app.amqp.router.route({}, "core.tasks.healthcheck_ping")
    assert options["queue"].name == "io"


def test_unrouted_task_falls_back_to_the_unconsumed_queue():
    """라우팅이 없는 잡은 'celery'나 'cpu' 같은 그럴듯한 큐로 조용히 쌓이지 않고, 아무
    worker-*도 구독하지 않는 함정 큐("unrouted")로 떨어진다(docker-compose.yml 확인).
    이 함정 큐 자체는 CELERY_TASK_QUEUES에 선언돼 있어야 한다 — 그래야 Celery 5.4가
    .delay() 디스패치 때 내부적으로 미리 조회하는 task_default_queue가 해소되고(실측
    확인: 안 그러면 라우팅이 멀쩡한 잡까지 전부 KeyError로 깨진다), 그 대신 아래
    test_every_registered_task_has_an_explicit_route가 "라우팅 누락"을 테스트 시점에
    잡는다."""
    options = celery_app.amqp.router.route({}, "some.totally.unrouted.task")
    assert options["queue"].name == "unrouted"


def test_every_registered_task_has_an_explicit_route():
    """새 배치 잡을 추가하고 CELERY_TASK_ROUTES에 큐를 안 적으면, 예전엔 디스패치
    시점(KeyError)에야 드러났다 — 이젠 "unrouted" 큐가 실제로 존재해 디스패치 자체는
    성공하지만 아무도 소비하지 않는 큐에 조용히 쌓이므로, 여기서 미리 잡는다."""
    task_names = {
        name for name in celery_app.tasks if not name.startswith("celery.")
    }
    missing = task_names - set(settings.CELERY_TASK_ROUTES)
    assert not missing, f"CELERY_TASK_ROUTES에 큐가 없는 잡: {missing}"
