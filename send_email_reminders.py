import os
import json
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from dotenv import load_dotenv

# Get the absolute path for the log file in the script's directory
script_dir = os.path.dirname(os.path.abspath(__file__))
log_file_path = os.path.join(script_dir, "email_reminder.log")

# Configure Logging
logging.basicConfig(
    level=logging.INFO,  # Change to DEBUG for more detailed logs during troubleshooting
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        # Append mode to preserve existing logs
        logging.FileHandler(log_file_path, mode='a'),
        logging.StreamHandler()  # Logs to the console
    ]
)

logging.info("Script started.")

# IMPORTANT: Removed or commented out the line that clears environment variables
# os.environ.clear()

# Load environment variables from .env file (optional for GitHub Actions)
load_dotenv()

# Retrieve SMTP server details from environment variables
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = os.getenv("SMTP_PORT")
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
LANDLORD_EMAIL = os.getenv("LANDLORD_EMAIL")

# Validate SMTP details
missing_smtp_vars = []
for var_name, var_value in [
    ("SMTP_SERVER", SMTP_SERVER),
    ("SMTP_PORT", SMTP_PORT),
    ("EMAIL_ADDRESS", EMAIL_ADDRESS),
    ("EMAIL_PASSWORD", EMAIL_PASSWORD),
    ("LANDLORD_EMAIL", LANDLORD_EMAIL)
]:
    if not var_value:
        missing_smtp_vars.append(var_name)

if missing_smtp_vars:
    logging.error(f"Missing SMTP environment variables: {
                  ', '.join(missing_smtp_vars)}.")
    exit(1)

# Validate TENANTS environment variable
TENANTS_ENV = os.getenv("TENANTS")
if not TENANTS_ENV:
    logging.error("TENANTS environment variable is missing.")
    TENANTS = []
else:
    try:
        TENANTS = json.loads(TENANTS_ENV)
        if not isinstance(TENANTS, list):
            logging.error(
                "TENANTS environment variable should be a JSON array of tenant objects.")
            TENANTS = []
    except json.JSONDecodeError as e:
        logging.error(
            f"TENANTS environment variable contains invalid JSON: {e}")
        TENANTS = []

logging.info(f"Loaded TENANTS: {TENANTS}")

try:
    SMTP_PORT = int(SMTP_PORT)
except ValueError:
    logging.error(f"Invalid SMTP_PORT value: {SMTP_PORT}")
    exit(1)

# Initialize counters and lists for tracking
success_count = 0
failure_count = 0
failed_tenants = []


def send_email_reminder(tenant):
    """
    Sends a rent payment reminder email to a single tenant.

    Args:
        tenant (dict): A dictionary containing tenant information.
    """
    global success_count, failure_count, failed_tenants
    try:
        # Validate required tenant fields
        required_fields = ["email", "name",
                           "payment_amount", "payment_description"]
        missing_fields = [
            field for field in required_fields if field not in tenant]
        if missing_fields:
            logging.error(f"Missing fields {
                          missing_fields} in tenant data: {tenant}")
            failure_count += 1
            failed_tenants.append({
                "tenant": tenant.get("name", "Unknown"),
                "email": tenant.get("email", "Unknown"),
                "reason": f"Missing fields: {', '.join(missing_fields)}"
            })
            return

        # Ensure payment_amount is a float
        try:
            payment_amount = float(tenant['payment_amount'])
        except (ValueError, TypeError):
            logging.error(f"Invalid payment_amount for tenant {tenant.get(
                'name', 'Unknown')}: {tenant.get('payment_amount')}")
            failure_count += 1
            failed_tenants.append({
                "tenant": tenant.get("name", "Unknown"),
                "email": tenant.get("email", "Unknown"),
                "reason": f"Invalid payment_amount: {tenant.get('payment_amount')}"
            })
            return

        subject = "Rent Payment Reminder"

        # HTML content with embedded banner and clickable buttons
        body = f"""\
        <html>
        <head>
            <style>
                /* Fallback styles can be placed here */
            </style>
        </head>
        <body>
            <p>Dear {tenant['name']},</p>
            <p>
                This is a friendly reminder that your rent payment of <strong>${payment_amount:.2f}</strong> is due soon.
            </p>
            <p>
                <strong>Payment Details:</strong><br>
                Property: {tenant.get('property_location', 'N/A')}<br>
                Description: {tenant['payment_description']}<br>
                Amount: <strong>${payment_amount:.2f}</strong>
            </p>
            <p>
                If payment is not received by the 5th day of the month, a 10% late fee will be imposed.
            </p>
            <p>
            <!-- Buttons Section -->
            <p>
                <a href="https://app.payrent.com/sign-in"
                   style="
                       display: inline-block;
                       padding: 10px 20px;
                       font-size: 16px;
                       color: #ffffff;
                       background-color: #ff9500;
                       text-decoration: none;
                       border-radius: 5px;
                       margin-right: 10px;
                   ">
                    Pay Now
                </a>
            </p>
                If you have any questions or need more information, please visit:
                <a href="https://segundorentalservices.net/" style="color: #1a0dab; text-decoration: none;">https://segundorentalservices.net/</a>
            </p>
            <p>Thank you!<br><br>Have a great day!</p>
        </body>
        </html>
        """

        # Create email message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = tenant["email"]

        # Attach the HTML content
        msg.attach(MIMEText(body, "html"))

        # Send email
        try:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                server.sendmail(
                    EMAIL_ADDRESS, tenant["email"], msg.as_string())
            logging.info(f"Reminder email sent successfully to {
                         tenant['name']} ({tenant['email']}).")
            success_count += 1
        except smtplib.SMTPException as smtp_err:
            logging.error(f"SMTP error when sending email to {
                          tenant.get('email', 'Unknown')}: {smtp_err}")
            failure_count += 1
            failed_tenants.append({
                "tenant": tenant.get("name", "Unknown"),
                "email": tenant.get("email", "Unknown"),
                "reason": f"SMTP error: {smtp_err}"
            })

    except Exception as e:
        logging.error(f"Unexpected error when sending email to {
                      tenant.get('email', 'Unknown')}: {e}")
        failure_count += 1
        failed_tenants.append({
            "tenant": tenant.get("name", "Unknown"),
            "email": tenant.get("email", "Unknown"),
            "reason": f"Unexpected error: {e}"
        })


def send_log_email():
    """
    Sends the log file as an attachment to the landlord.
    """
    try:
        subject = "Email Reminder Logs - Execution Summary"
        body = f"""Hello,

Please find attached the log file for the latest execution of the email reminder script.

Best regards,
Your Automated Email System
"""

        # Create a multipart message
        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = LANDLORD_EMAIL

        # Attach the body text
        msg.attach(MIMEText(body, "plain"))

        # Attach the log file
        if os.path.isfile(log_file_path):
            with open(log_file_path, "rb") as log_file:
                part = MIMEApplication(
                    log_file.read(), Name=os.path.basename(log_file_path))
                part['Content-Disposition'] = f'attachment; filename="{
                    os.path.basename(log_file_path)}"'
                msg.attach(part)
        else:
            logging.error(f"Log file not found at {
                          log_file_path}. Cannot attach to log email.")

        # Send log email
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, LANDLORD_EMAIL, msg.as_string())

        logging.info("Log email sent successfully to the landlord.")

    except smtplib.SMTPException as smtp_err:
        logging.error(f"SMTP error when sending log email: {smtp_err}")
    except Exception as e:
        logging.error(f"Unexpected error when sending log email: {e}")


def send_emails_to_all_tenants():
    """
    Sends reminder emails to all tenants.
    """
    if not TENANTS:
        logging.warning("No tenants found to send emails.")
        return

    for tenant in TENANTS:
        send_email_reminder(tenant)


def check_and_send_email():
    """
    Executes the entire email sending process: reminders and logs.
    """
    send_emails_to_all_tenants()
    send_log_email()


if __name__ == "__main__":
    check_and_send_email()
    logging.info("Script execution completed.")
