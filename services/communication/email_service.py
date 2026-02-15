import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from uuid import UUID
from config.settings import settings
from utils.logger import setup_logger

logger = setup_logger(__name__)


class EmailService:
    def __init__(self):
        self.smtp_host = "smtp.gmail.com"
        self.smtp_port = 587
        self.smtp_user = "admin@tastebud-co.com"
        self.smtp_password = "qdpgxhxyvqngzrss"
        self.from_email = "admin@tastebud-co.com"
        self.from_name = "TasteBud"
    
    def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None
    ) -> bool:
        try:
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = f"{self.from_name} <{self.from_email}>"
            message["To"] = to_email
            
            if text_body:
                part1 = MIMEText(text_body, "plain")
                message.attach(part1)
            
            part2 = MIMEText(html_body, "html")
            message.attach(part2)
            
            server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30)
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(self.smtp_user, self.smtp_password)
            server.sendmail(self.from_email, [to_email], message.as_string())
            server.quit()
            
            logger.info("Email sent successfully", extra={"to": to_email, "subject": subject})
            return True
            
        except Exception as e:
            logger.error(
                "Failed to send email",
                extra={"to": to_email, "error": str(e), "error_type": type(e).__name__},
                exc_info=True
            )
            return False
    
    def send_otp_code(self, to_email: str, code: str) -> bool:
        subject = "Your TasteBud Login Code"
        
        text_body = f"""
        Your TasteBud verification code is: {code}
        
        This code will expire in 10 minutes.
        
        If you didn't request this code, please ignore this email.
        
        Happy tasting!
        - The TasteBud Team
        """
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                    line-height: 1.6;
                    color: #e5e7eb;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #111827;
                }}
                .container {{
                    background: linear-gradient(135deg, #111827 0%, #1f2937 50%, #111827 100%);
                    border-radius: 16px;
                    padding: 40px;
                    text-align: center;
                    color: #e5e7eb;
                    border: 1px solid #374151;
                }}
                .logo {{
                    font-size: 48px;
                    font-weight: bold;
                    margin-bottom: 20px;
                    background: linear-gradient(135deg, #f97316 0%, #ef4444 100%);
                    -webkit-background-clip: text;
                    -webkit-text-fill-color: transparent;
                    background-clip: text;
                }}
                .code-container {{
                    background: #1f2937;
                    color: #f97316;
                    padding: 30px;
                    border-radius: 12px;
                    margin: 30px 0;
                    border: 2px solid #374151;
                }}
                .code {{
                    font-size: 48px;
                    font-weight: bold;
                    letter-spacing: 8px;
                    color: #f97316;
                    font-family: 'Courier New', monospace;
                }}
                .message {{
                    font-size: 18px;
                    margin: 20px 0;
                    color: #e5e7eb;
                }}
                .message h2 {{
                    color: #f97316;
                }}
                .footer {{
                    font-size: 14px;
                    color: #9ca3af;
                    margin-top: 30px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="logo">️ TasteBud</div>
                <div class="message">
                    <h2>Your Login Code</h2>
                    <p>Enter this code to access your personalized food recommendations</p>
                </div>
                <div class="code-container">
                    <div class="code">{code}</div>
                </div>
                <p>This code will expire in <strong>10 minutes</strong></p>
                <div class="footer">
                    <p>If you didn't request this code, please ignore this email.</p>
                    <p>Happy tasting! </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return self.send_email(to_email, subject, html_body, text_body)
    
    def send_magic_link(self, to_email: str, token: str) -> bool:
        magic_link = f"{settings.FRONTEND_URL}/auth/verify?token={token}"
        subject = "Your TasteBud Magic Link"
        
        text_body = f"""
        Click the link below to log in to TasteBud:
        
        {magic_link}
        
        This link will expire in 10 minutes.
        
        If you didn't request this link, please ignore this email.
        
        Happy tasting!
        - The TasteBud Team
        """
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .container {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    border-radius: 16px;
                    padding: 40px;
                    text-align: center;
                    color: white;
                }}
                .logo {{
                    font-size: 48px;
                    font-weight: bold;
                    margin-bottom: 20px;
                }}
                .message {{
                    font-size: 18px;
                    margin: 20px 0;
                }}
                .button {{
                    display: inline-block;
                    background: white;
                    color: #667eea;
                    padding: 16px 40px;
                    border-radius: 8px;
                    text-decoration: none;
                    font-weight: bold;
                    margin: 30px 0;
                    font-size: 18px;
                }}
                .button:hover {{
                    background: #f0f0f0;
                }}
                .footer {{
                    font-size: 14px;
                    color: rgba(255, 255, 255, 0.8);
                    margin-top: 30px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="logo">️ TasteBud</div>
                <div class="message">
                    <h2>Your Magic Link is Ready</h2>
                    <p>Click the button below to access your personalized food recommendations</p>
                </div>
                <a href="{magic_link}" class="button">Log In to TasteBud</a>
                <p style="font-size: 14px; margin-top: 20px;">
                    This link will expire in <strong>10 minutes</strong>
                </p>
                <div class="footer">
                    <p>If you didn't request this link, please ignore this email.</p>
                    <p>Happy tasting! </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return self.send_email(to_email, subject, html_body, text_body)
    
    def verify_feedback_token(self, token: str) -> Optional[UUID]:
        from services.communication.email_followup_service import email_followup_service
        return email_followup_service.verify_feedback_token(token)


email_service = EmailService()
