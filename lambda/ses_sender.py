
def send_summary_email(recipient_email: str, subject: str, html_body: str) -> dict:
    """Send the summary email"""
    _ = (recipient_email, subject, html_body)
    return {"message_id": None}
