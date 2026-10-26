from typing import Optional
from taskiq_redis import ListQueueBroker
from src.config import settings

# Primary Taskiq broker backed by Redis List queue
broker = ListQueueBroker(
    url=settings.REDIS_URL,
    queue_name="lokachakra_tasks",
)

# Dead-letter queue broker for poisoned/failed tasks requiring human audit
dlq_broker = ListQueueBroker(
    url=settings.REDIS_URL,
    queue_name="lokachakra_dlq",
)


async def send_to_dlq(task_name: str, payload: dict, error_message: str) -> None:
    """Dispatches unrecoverable or failed task records to the Dead-Letter Queue."""
    await dlq_broker.kick(
        dlq_broker.find_task(task_name),
        {"payload": payload, "error": error_message},
    )
