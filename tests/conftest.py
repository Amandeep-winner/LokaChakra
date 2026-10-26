import os
import pytest

# Ensure APP_ENV is test during test execution
os.environ["APP_ENV"] = "test"


@pytest.fixture(scope="session")
def sample_linkedin_csv() -> str:
    return """Notes:
Some disclaimer line 1 from LinkedIn
Some disclaimer line 2 from LinkedIn
First Name,Last Name,URL,Email Address,Company,Position,Connected On
Rohan,Verma,https://www.linkedin.com/in/rohanverma,rohan@example.com,Razorpay,Software Engineer,10 Oct 2024
Ananya,Iyer,https://www.linkedin.com/in/ananyaiyer,,Flipkart,Product Manager,12 Oct 2024
"""


@pytest.fixture(scope="session")
def sample_whatsapp_chat() -> str:
    return """[12/10/24, 10:15:30 AM] Rohan: Hey, let's catch up at the Starbucks in Indiranagar.
[12/10/24, 10:16:10 AM] Amandeep: Sounds great, see you at 5pm.
[13/10/24, 11:00:22 AM] Vikram: Siddharth joined Stripe as staff engineer yesterday!
[13/10/24, 11:05:00 AM] Amandeep: Wow congrats to him.
"""
