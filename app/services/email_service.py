"""
Email Service for Terraform Cloud Agent

Handles sending approval emails with Terraform files attached.
"""
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from pathlib import Path
import zipfile
import io
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

from app.core.config import (
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASSWORD,
    SMTP_FROM_EMAIL,
    SMTP_FROM_NAME,
    SEND_EMAIL_ALERTS,
    APPROVAL_TOKEN_SECRET,
    APPROVAL_TOKEN_EXPIRY_HOURS,
    BASE_URL
)

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending emails via SMTP"""
    
    def __init__(self):
        self.smtp_host = SMTP_HOST
        self.smtp_port = SMTP_PORT
        self.smtp_user = SMTP_USER
        self.smtp_password = SMTP_PASSWORD
        self.from_email = SMTP_FROM_EMAIL or SMTP_USER
        self.from_name = SMTP_FROM_NAME
        self.enabled = SEND_EMAIL_ALERTS and all([SMTP_HOST, SMTP_USER, SMTP_PASSWORD])
        self.serializer = URLSafeTimedSerializer(APPROVAL_TOKEN_SECRET)
        
        if not self.enabled:
            logger.warning("Email service is disabled. Check SMTP configuration.")
    
    def generate_approval_token(self, run_id: str, user_email: str, action: str = "approve") -> str:
        """Generate a signed token for approve/reject links"""
        data = {
            "run_id": run_id,
            "user_email": user_email,
            "action": action,
            "timestamp": datetime.utcnow().isoformat()
        }
        return self.serializer.dumps(data)
    
    def verify_approval_token(self, token: str) -> Optional[Dict]:
        """Verify and decode an approval token"""
        try:
            # Token expires after configured hours
            max_age = APPROVAL_TOKEN_EXPIRY_HOURS * 3600
            data = self.serializer.loads(token, max_age=max_age)
            return data
        except SignatureExpired:
            logger.error("Approval token has expired")
            return None
        except BadSignature:
            logger.error("Invalid approval token signature")
            return None
    
    def create_terraform_zip(self, terraform_files: Dict[str, str]) -> bytes:
        """Create a ZIP file from Terraform files"""
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for filename, content in terraform_files.items():
                zip_file.writestr(filename, content)
        return zip_buffer.getvalue()
    
    def create_approval_email_html(
        self,
        user_email: str,
        run_id: str,
        terraform_summary: Dict,
        approve_token: str,
        reject_token: str
    ) -> str:
        """Create HTML email for Terraform approval"""
        
        approve_url = f"{BASE_URL}/approve/{approve_token}"
        reject_url = f"{BASE_URL}/reject/{reject_token}"
        
        # Extract resource summary
        resources = terraform_summary.get("resources", [])
        resource_list = ""
        for resource in resources[:10]:  # Show first 10
            resource_list += f"<li><strong>{resource.get('type', 'Unknown')}</strong>: {resource.get('name', 'unnamed')}</li>"
        
        if len(resources) > 10:
            resource_list += f"<li><em>... and {len(resources) - 10} more resources</em></li>"
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 30px;
                    text-align: center;
                    border-radius: 8px 8px 0 0;
                }}
                .content {{
                    background: #f9fafb;
                    padding: 30px;
                    border: 1px solid #e5e7eb;
                }}
                .summary {{
                    background: white;
                    padding: 20px;
                    border-radius: 6px;
                    margin: 20px 0;
                    border-left: 4px solid #667eea;
                }}
                .resources {{
                    background: white;
                    padding: 20px;
                    border-radius: 6px;
                    margin: 20px 0;
                }}
                .resources ul {{
                    list-style: none;
                    padding: 0;
                }}
                .resources li {{
                    padding: 8px 0;
                    border-bottom: 1px solid #f3f4f6;
                }}
                .button-container {{
                    text-align: center;
                    margin: 30px 0;
                }}
                .button {{
                    display: inline-block;
                    padding: 14px 32px;
                    margin: 0 10px;
                    text-decoration: none;
                    border-radius: 6px;
                    font-weight: 600;
                    font-size: 16px;
                }}
                .approve-btn {{
                    background: #10b981;
                    color: white;
                }}
                .approve-btn:hover {{
                    background: #059669;
                }}
                .reject-btn {{
                    background: #ef4444;
                    color: white;
                }}
                .reject-btn:hover {{
                    background: #dc2626;
                }}
                .footer {{
                    text-align: center;
                    color: #6b7280;
                    font-size: 14px;
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 1px solid #e5e7eb;
                }}
                .warning {{
                    background: #fef3c7;
                    border-left: 4px solid #f59e0b;
                    padding: 15px;
                    margin: 20px 0;
                    border-radius: 4px;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Terraform Configuration Ready for Review</h1>
            </div>
            
            <div class="content">
                <p>Hello,</p>
                
                <p>Your Terraform configuration has been generated and is ready for approval.</p>
                
                <div class="summary">
                    <h3>Run Details</h3>
                    <p><strong>Run ID:</strong> {run_id}</p>
                    <p><strong>Total Resources:</strong> {len(resources)}</p>
                    <p><strong>Generated:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>
                </div>
                
                <div class="resources">
                    <h3>Resources to be Created</h3>
                    <ul>
                        {resource_list}
                    </ul>
                </div>
                
                <div class="warning">
                    <strong>Important:</strong> Please review the attached Terraform files carefully before approving.
                    This will create real infrastructure resources in your cloud account.
                </div>
                
                <div class="button-container">
                    <a href="{approve_url}" class="button approve-btn">Approve</a>
                    <a href="{reject_url}" class="button reject-btn">Reject</a>
                </div>
                
                <div class="footer">
                    <p>This approval link expires in {APPROVAL_TOKEN_EXPIRY_HOURS} hours.</p>
                    <p>Terraform Cloud Agent • Automated Infrastructure as Code</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html
    
    def send_terraform_approval_email(
        self,
        to_email: str,
        run_id: str,
        terraform_files: Dict[str, str],
        terraform_summary: Dict
    ) -> bool:
        """Send Terraform approval email with files attached"""
        
        if not self.enabled:
            logger.error("Email service is not enabled")
            return False
        
        try:
            # Generate tokens
            approve_token = self.generate_approval_token(run_id, to_email, action="approve")
            reject_token = self.generate_approval_token(run_id, to_email, action="reject")
            
            # Create message
            msg = MIMEMultipart('mixed')  # 'mixed' required for binary attachment
            msg['Subject'] = f'Terraform Configuration Approval Required - Run {run_id[:8]}'
            msg['From'] = f'{self.from_name} <{self.from_email}>'
            msg['To'] = to_email
            
            # Create HTML body
            html_body = self.create_approval_email_html(
                to_email,
                run_id,
                terraform_summary,
                approve_token,
                reject_token
            )
            
            # Attach HTML
            html_part = MIMEText(html_body, 'html')
            msg.attach(html_part)
            
            # Create and attach ZIP file
            zip_data = self.create_terraform_zip(terraform_files)
            zip_attachment = MIMEApplication(zip_data, _subtype='zip')
            zip_attachment.add_header(
                'Content-Disposition',
                'attachment',
                filename=f'terraform_{run_id[:8]}.zip'
            )
            msg.attach(zip_attachment)
            
            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            logger.info(f"Approval email sent to {to_email} for run {run_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send approval email: {str(e)}")
            return False
    
    def send_approval_confirmation_email(
        self,
        to_email: str,
        run_id: str,
        approved: bool,
        reason: Optional[str] = None
    ) -> bool:
        """Send confirmation email after approval/rejection"""
        
        if not self.enabled:
            return False
        
        try:
            status = "Approved" if approved else "Rejected"
            indicator = "[APPROVED]" if approved else "[REJECTED]"
            color = "#10b981" if approved else "#ef4444"
            
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{
                        font-family: sans-serif;
                        max-width: 600px;
                        margin: 0 auto;
                        padding: 20px;
                    }}
                    .header {{
                        background: {color};
                        color: white;
                        padding: 20px;
                        text-align: center;
                        border-radius: 8px;
                    }}
                    .content {{
                        padding: 30px;
                        background: #f9fafb;
                        margin-top: 20px;
                    }}
                </style>
            </head>
            <body>
                <div class="header">
                    <h1>{indicator} Terraform Configuration {status}</h1>
                </div>
                <div class="content">
                    <p>Your Terraform configuration (Run ID: {run_id}) has been <strong>{status.lower()}</strong>.</p>
                    {f'<p><strong>Reason:</strong> {reason}</p>' if reason else ''}
                    <p>You can view the details in your Terraform Cloud Agent dashboard.</p>
                </div>
            </body>
            </html>
            """
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f'Terraform Configuration {status} - Run {run_id[:8]}'
            msg['From'] = f'{self.from_name} <{self.from_email}>'
            msg['To'] = to_email
            msg.attach(MIMEText(html, 'html'))
            
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            logger.info(f"Confirmation email sent to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send confirmation email: {str(e)}")
            return False


# Global email service instance
email_service = EmailService()
