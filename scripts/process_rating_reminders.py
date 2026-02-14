from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import Session
from config.database import get_session_maker
from services.rating_reminder_service import RatingReminderService
from utils.logger import setup_logger

logger = setup_logger(__name__)


def process_rating_reminders():
    SessionMaker = get_session_maker()
    session = SessionMaker()
    
    try:
        service = RatingReminderService()
        sent_count = service.process_pending_reminders(session)
        
        logger.info(
            "Rating reminder processing complete",
            extra={"sent_count": sent_count}
        )
        
        return sent_count
        
    except Exception as e:
        logger.error(
            "Error processing rating reminders",
            extra={"error": str(e)},
            exc_info=True
        )
        raise
    finally:
        session.close()


if __name__ == "__main__":
    process_rating_reminders()
