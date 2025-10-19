import os
from huggingface_hub import login
from dotenv import load_dotenv
load_dotenv()

def hf_login_from_env() -> bool:
    token = os.getenv("HUGGINGFACE_HUB_TOKEN")
    if not token:
        return False
    try:
        login(token=token, add_to_git_credential=False)
        return True
    except Exception:
        return False
