import aiosmtplib
from email.mime.text import MIMEText
from fastapi import HTTPException


async def send_email(to: str, subject: str, body: str):
    sender = "mohsinrashid64@gmail.com"  # Replace with your Gmail address
    password = "svmx bxhr mzod orlc"  # Replace with your Gmail/App Password
    smtp_server = "smtp.gmail.com"
    smtp_port = 587  # Use 465 for SSL

    # try:
        # Create the email content
    msg = MIMEText(body)
    msg["From"] = "example@gmail.com"
    msg["To"] = to
    msg["Subject"] = subject


    await aiosmtplib.send(
        msg,
        hostname="smtp.gmail.com",
        port=587,
        username="mohsinrashid64@gmail.com",
        password = "svmx bxhr mzod orlc",  # Replace with your Gmail/App Password
        start_tls=True,
    )

        # Connect to the SMTP server
        # with smtplib.SMTP(smtp_server, smtp_port) as server:
        #     server.starttls()  # Upgrade the connection to TLS
        #     server.login(sender, password)  # Log in to the SMTP server
        #     server.sendmail(sender, [to], msg.as_string())  # Send the email
    # except smtplib.SMTPException as e:
    #     raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")
