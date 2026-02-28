"""Request Access tab — shown only to users with the no_access role."""
import logging
from pathlib import Path
from urllib.parse import quote

import gradio as gr
import yaml

logger = logging.getLogger(__name__)
_ROLES_PATH = Path(__file__).parent.parent / "governance" / "roles.yaml"


def _get_admin_email() -> str:
    try:
        with open(_ROLES_PATH) as f:
            config = yaml.safe_load(f)
        return config.get("admin_email", "annakamcclelland@gmail.com")
    except Exception:
        return "annakamcclelland@gmail.com"


def build() -> None:
    """Build the Request Access tab."""
    admin_email = _get_admin_email()

    gr.Markdown("## Request Access")
    gr.Markdown(
        "You do not currently have access to the **Predictive Maintenance Intelligence Hub**.\n\n"
        "Click the button below to send an access request to the administrator."
    )

    user_display = gr.Markdown("")
    request_btn = gr.Button("Request Access", variant="primary", size="lg")
    result_html = gr.HTML(visible=False)

    def on_load(request: gr.Request):
        from services import auth_service
        user = auth_service.get_user_from_request(request)
        email = user["email"] if user else "unknown"
        return f"**Your account:** `{email}`"

    def send_request(request: gr.Request):
        from services import auth_service
        user = auth_service.get_user_from_request(request)
        email = user["email"] if user else "unknown"

        subject = "Access Request — Predictive Maintenance Hub"
        body = (
            f"Hello,\n\n"
            f"I would like to request access to the Predictive Maintenance Intelligence Hub.\n\n"
            f"User email: {email}\n\n"
            f"Thank you."
        )
        mailto = f"mailto:{admin_email}?subject={quote(subject)}&body={quote(body)}"

        html = f"""
        <div style="padding:1rem;background:#e8f5e9;border-radius:8px;border-left:4px solid #43A047;margin-top:1rem;">
            <p style="margin:0 0 0.5rem;font-weight:600;">Access request ready!</p>
            <p style="margin:0 0 0.75rem;">Click below to open your email client with a pre-filled request:</p>
            <a href="{mailto}"
               style="display:inline-block;padding:0.5rem 1.25rem;background:#43A047;color:white;
                      text-decoration:none;border-radius:4px;font-weight:600;">
                Open Email Client
            </a>
            <p style="margin-top:0.75rem;font-size:0.85rem;color:#555;">
                Or email the administrator directly:
                <strong><a href="mailto:{admin_email}" style="color:#1a73e8;">{admin_email}</a></strong>
            </p>
        </div>
        """
        return gr.update(value=html, visible=True)

    request_btn.click(fn=send_request, outputs=[result_html])

    # Return (output, load_fn) so app.py can wire demo.load()
    return [user_display], on_load
