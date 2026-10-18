import pytest

from config.celery import app as celery_app


def test_routed_task_resolves_to_its_declared_queue():
    options = celery_app.amqp.router.route({}, "core.tasks.healthcheck_ping")
    assert options["queue"].name == "io"


def test_unrouted_task_raises_immediately_instead_of_defaulting():
    """라우팅이 없는 잡은 'celery'나 'cpu' 같은 그럴듯한 기본 큐에 조용히 쌓이지 않고,
    task_create_missing_queues=False + 미선언 기본 큐("unrouted") 조합으로 즉시 에러가 난다."""
    with pytest.raises(KeyError):
        celery_app.amqp.router.route({}, "some.totally.unrouted.task")
