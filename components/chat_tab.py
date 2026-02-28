"""Ask Your Data tab — Genie → Bedrock conversational interface."""
import re
import logging

import gradio as gr
import pandas as pd

from services import ai_service, auth_service, audit_service

logger = logging.getLogger(__name__)

# Decimal places for numeric display in chat (query results + numbers in text)
_DECIMAL_PLACES = 4

# Max rows to show as markdown table inline in the chat
_IN_CHAT_TABLE_MAX_ROWS = 25


def _round_df_decimals(df: pd.DataFrame, decimals: int = _DECIMAL_PLACES) -> pd.DataFrame:
    """Round float columns to the given number of decimal places; leave other dtypes unchanged."""
    if df is None or len(df) == 0:
        return df
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].round(decimals)
    return out


def _round_numbers_in_text(text: str, decimals: int = _DECIMAL_PLACES) -> str:
    """Round numbers with more than `decimals` decimal places (e.g. 0.03921234 → 0.0392)."""
    if not text or decimals < 0:
        return text

    def repl(m):
        try:
            return str(round(float(m.group(1)), decimals))
        except ValueError:
            return m.group(0)

    # Match numbers that have a decimal point and at least (decimals+1) decimal places
    pattern = r"(\d+\.\d{" + str(decimals + 1) + r",})"
    return re.sub(pattern, repl, text)


def _df_to_markdown_table(df: pd.DataFrame, max_rows: int = _IN_CHAT_TABLE_MAX_ROWS) -> str:
    """Convert DataFrame to a markdown table string; limit rows for in-chat display."""
    if df is None or len(df) == 0:
        return ""
    head = df.head(max_rows)
    cols = list(head.columns)
    sep = " | "
    header = "| " + sep.join(str(c).replace("|", "\\|") for c in cols) + " |"
    divider = "| " + sep.join("---" for _ in cols) + " |"
    rows = []
    for _, row in head.iterrows():
        cells = [str(row[c]).replace("|", "\\|") for c in cols]
        rows.append("| " + sep.join(cells) + " |")
    table = "\n".join([header, divider] + rows)
    if len(df) > max_rows:
        table += f"\n_… and {len(df) - max_rows} more row(s)._"
    return table


_EXAMPLE_QUESTIONS = [
    "Which machine type has the highest failure rate?",
    "Show me the top 10 CNC machines by tool wear and whether they failed.",
    "What is the average torque when a machine failure occurs?",
    "How many power failures happened across all CNC machines?"
    ]


def build(conv_id_state: gr.State, schema_context: str = "") -> None:
    """Build the Ask Your Data tab inside a gr.Blocks context."""

    gr.Markdown("## Ask Your Data")
    gr.Markdown("Ask in plain English; get answers and tables — no code.")
    gr.Markdown("_Data questions may take 5–15 seconds while we query your data._")

    # Conversation window: chat + input and buttons at the bottom
    with gr.Column(variant="panel", elem_id="chat-panel-column"):
        # like_user_message=False hides like/dislike on user messages (Gradio 4.45+);
        # older Gradio ignores it via try/except
        try:
            chatbot = gr.Chatbot(
                label="",
                height=400,
                type="messages",
                render_markdown=True,
                show_label=False,
                like_user_message=False,
            )
        except TypeError:
            chatbot = gr.Chatbot(
                label="",
                height=400,
                type="messages",
                render_markdown=True,
                show_label=False,
            )
        msg_box = gr.Textbox(
            placeholder="e.g. Which CNC machines have the most tool wear failures?",
            label="Your question",
            max_lines=3,
        )
        with gr.Row(elem_id="chat-buttons-row"):
            submit_btn = gr.Button("Ask", variant="primary")
            clear_btn = gr.Button("Clear Chat", variant="secondary")
        source_label = gr.Markdown("", elem_id="chat-source-label")
        gr.Markdown("**Example questions:**", elem_id="example-questions-heading")
        with gr.Row(elem_id="example-questions-row"):
            for q in _EXAMPLE_QUESTIONS[:3]:
                gr.Button(q, size="sm").click(
                    fn=lambda question=q: question,
                    outputs=[msg_box],
                )

    # ── Respond handler ────────────────────────────────────────────────────────
    def respond(message: str, history: list, conv_id: str | None,
                request: gr.Request) -> tuple:
        message = message.strip()
        if not message or len(message) > 2000:
            return history, message, conv_id, ""

        user  = auth_service.get_user_from_request(request)
        email = user["email"] if user else "unknown"
        role  = user["role"]  if user else "viewer"

        result = ai_service.chat_with_data(
            question=message,
            conversation_id=conv_id,
            schema_context=schema_context,
        )

        # Explanation text only — no SQL/code in chat window. Ensure string for Gradio Chatbot.
        raw_reply = result.text if not result.error else (
            "Sorry, I could not answer that question. Please try rephrasing it."
        )
        if isinstance(raw_reply, dict):
            reply = raw_reply.get("content", raw_reply.get("text", str(raw_reply)))
        elif isinstance(raw_reply, list):
            reply = "\n".join(str(x) for x in raw_reply) if raw_reply else ""
        else:
            reply = str(raw_reply) if raw_reply is not None else ""
        reply = reply.strip() or "No response."
        reply = _round_numbers_in_text(reply, _DECIMAL_PLACES)

        # Round query results to 4 decimal places for display
        display_df = None
        if result.dataframe is not None and len(result.dataframe) > 0:
            display_df = _round_df_decimals(result.dataframe, _DECIMAL_PLACES)

        audit_service.log_event(
            action_type="CHAT",
            user_email=email, user_role=role,
            ai_source=result.source,
            source_tables="(AI-generated query)",
            query_text=result.sql or message,
            row_count=len(result.dataframe) if result.dataframe is not None else 0,
        )

        # Build assistant message: text + optional inline table (query results under the text)
        assistant_content = reply
        if display_df is not None and len(display_df) > 0:
            table_md = _df_to_markdown_table(display_df, _IN_CHAT_TABLE_MAX_ROWS)
            if table_md:
                assistant_content = reply + "\n\n" + table_md

        new_history = history + [
            {"role": "user",      "content": message},
            {"role": "assistant", "content": assistant_content},
        ]

        source_md = f"_Answered by: **{result.source.capitalize()}**_"

        return new_history, "", result.conversation_id, source_md

    submit_btn.click(
        fn=respond,
        inputs=[msg_box, chatbot, conv_id_state],
        outputs=[chatbot, msg_box, conv_id_state, source_label],
    )
    msg_box.submit(
        fn=respond,
        inputs=[msg_box, chatbot, conv_id_state],
        outputs=[chatbot, msg_box, conv_id_state, source_label],
    )
    clear_btn.click(
        fn=lambda: ([], "", None, ""),
        outputs=[chatbot, msg_box, conv_id_state, source_label],
    )

    # ── Feedback handler (Like/Dislike on assistant messages) ────────────────────
    def on_feedback(
        _chatbot_value: list,
        like_data: gr.LikeData,
        conv_id: str | None,
        request: gr.Request,
    ) -> None:
        """Log FEEDBACK to audit trail when user likes/dislikes an assistant message."""
        try:
            idx = like_data.index
            # Handle different index types: tuple, list, int, or None
            if isinstance(idx, (tuple, list)):
                idx = idx[0] if idx else 0
            else:
                idx = int(idx) if idx is not None else 0
            # Only allow feedback on assistant messages, not user messages
            if not _chatbot_value or idx < 0 or idx >= len(_chatbot_value):
                return
            msg = _chatbot_value[idx]
            if not isinstance(msg, dict) or msg.get("role") != "assistant":
                return
            liked = like_data.liked
            if isinstance(liked, str):
                liked = liked.strip().lower() in ("true", "like", "1", "yes")
            else:
                liked = bool(liked)
            
            user = auth_service.get_user_from_request(request)
            email = user["email"] if user else "unknown"
            role = user["role"] if user else "viewer"
            audit_service.log_event(
                action_type="FEEDBACK",
                user_email=email,
                user_role=role,
                query_text=conv_id or "",
                message_index=idx,
                liked=liked,
            )
        except Exception as exc:
            logger.warning("Feedback logging failed: %s", exc, exc_info=True)

    chatbot.like(
        on_feedback,
        inputs=[chatbot, conv_id_state],
        outputs=[],
    )
