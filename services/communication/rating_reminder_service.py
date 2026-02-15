from __future__ import annotations
from typing import Optional
from datetime import datetime, timedelta
from sqlmodel import Session, select
from models import User
from models.session import RecommendationSession
from utils.logger import setup_logger
from services.communication.email_service import EmailService

logger = setup_logger(__name__)


class RatingReminderService:
    def __init__(self):
        self.email_service = EmailService()
    
    def schedule_rating_reminder(
        self,
        session: Session,
        rec_session: RecommendationSession,
        user: User
    ) -> None:
        if not rec_session:
            raise ValueError("rec_session is required to schedule rating reminder")
        
        if not user:
            raise ValueError("user is required to schedule rating reminder")
        
        reminder_time = datetime.utcnow() + timedelta(hours=1)
        rec_session.email_scheduled_at = reminder_time
        
        session.add(rec_session)
        session.commit()
        
        logger.info(
            "Rating reminder scheduled",
            extra={
                "user_id": str(user.id),
                "session_id": str(rec_session.id),
                "scheduled_for": reminder_time.isoformat()
            }
        )
    
    def process_pending_reminders(self, session: Session) -> int:
        now = datetime.utcnow()
        
        pending_sessions = session.exec(
            select(RecommendationSession)
            .where(RecommendationSession.email_scheduled_at <= now)
            .where(RecommendationSession.email_sent_at.is_(None))
            .where(RecommendationSession.status == "completed")
        ).all()
        
        sent_count = 0
        
        for rec_session in pending_sessions:
            try:
                user = session.get(User, rec_session.user_id)
                if not user:
                    continue
                
                self.send_rating_request(session, rec_session, user)
                sent_count += 1
                
            except Exception as e:
                logger.error(
                    "Failed to send rating reminder",
                    extra={
                        "session_id": str(rec_session.id),
                        "error": str(e)
                    },
                    exc_info=True
                )
        
        logger.info(
            "Processed pending rating reminders",
            extra={
                "total_pending": len(pending_sessions),
                "sent_count": sent_count
            }
        )
        
        return sent_count
    
    def send_rating_request(
        self,
        session: Session,
        rec_session: RecommendationSession,
        user: User
    ) -> None:
        if not user.email:
            raise ValueError("User email is required to send rating reminder")
        
        rating_url = f"https://app.tastebud.com/feedback/{rec_session.id}"
        
        subject = "How was your meal? Share your experience!"
        
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #E85D75;">How was your meal?</h2>
            
            <p>Hi there!</p>
            
            <p>We hope you enjoyed your meal! Your feedback helps us provide better recommendations tailored to your taste.</p>
            
            <p>It will only take a minute to share your experience:</p>
            
            <div style="text-align: center; margin: 30px 0;">
                <a href="{rating_url}" 
                   style="background-color: #E85D75; color: white; padding: 15px 30px; 
                          text-decoration: none; border-radius: 8px; display: inline-block;
                          font-weight: bold;">
                    Rate Your Meal
                </a>
            </div>
            
            <p style="color: #666; font-size: 14px;">
                This link will expire in 7 days. If you have any questions, just reply to this email.
            </p>
            
            <p style="margin-top: 30px;">
                Thank you,<br>
                <strong>The TasteBud Team</strong>
            </p>
        </body>
        </html>
        """
        
        text_body = f"""
        How was your meal?
        
        Hi there!
        
        We hope you enjoyed your meal! Your feedback helps us provide better recommendations tailored to your taste.
        
        Please rate your meal by clicking this link:
        {rating_url}
        
        This link will expire in 7 days.
        
        Thank you,
        The TasteBud Team
        """
        
        self.email_service.send_email(
            to_email=user.email,
            subject=subject,
            html_body=html_body,
            text_body=text_body
        )
        
        rec_session.email_sent_at = datetime.utcnow()
        session.add(rec_session)
        session.commit()
        
        logger.info(
            "Rating request email sent",
            extra={
                "user_id": str(user.id),
                "session_id": str(rec_session.id),
                "email": user.email
            }
        )
    
    def get_pending_feedback_url(self, session_id: str) -> str:
        return f"https://app.tastebud.com/feedback/{session_id}"
