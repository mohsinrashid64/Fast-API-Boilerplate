import asyncio
import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)


def _send_sms_sync(to: str, message: str) -> dict:
    sns_client = boto3.client(
        "sns",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION,
    )
    try:
        response = sns_client.publish(PhoneNumber=to, Message=message)
    except (BotoCoreError, ClientError) as error:
        raise RuntimeError(f"Failed to send SMS: {error}") from error
    return {"message_id": response.get("MessageId"), "status": "success"}


async def send_sms(to: str, message: str) -> dict:
    """Send an SMS via AWS SNS. `to` must be E.164 (e.g. "+1234567890").

    boto3 is blocking, so it runs in a worker thread. If AWS isn't configured in
    a non-production environment, the SMS is logged instead of sent.
    """
    if not (settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY):
        if settings.is_production:
            raise RuntimeError("AWS SNS is not configured")
        logger.warning("AWS not configured; SMS to %s not sent: %s", to, message)
        return {"message_id": None, "status": "skipped"}
    return await asyncio.to_thread(_send_sms_sync, to, message)
