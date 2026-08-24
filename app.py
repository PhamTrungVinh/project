import streamlit as st
from langchain.messages import HumanMessage, AIMessage
from hitl import get_pending_action, approve_action, reject_action, needs_auto_resume
from config import HITL_ENABLED
from memory import clear_facts, clear_episodes, clear_working_memory
import uuid
from graph import build_graph
import db
from logger import agent_logger

def process_graph_result(result, config):
    """Sau mỗi lần invoke/resume, kiểm tra graph đã thực sự kết thúc (END)
    hay lại dừng ở 1 interrupt tiếp theo. Trả về (answer, still_pending)."""
    # Tool không nhạy cảm thì tự resume tiếp
    if needs_auto_resume(app, config):
        result = approve_action(app, config)

    pending = get_pending_action(app, config)
    if pending:
        # Graph dừng lại LẦN NỮA -> chưa có câu trả lời cuối, cần user xác nhận tiếp
        return None, {"node": pending[0], "tool_calls": pending[1], "thread_id": config["configurable"]["thread_id"]}

    # Graph đã chạy tới END thật sự -> lúc này lấy AIMessage cuối mới đáng tin
    answer = ""
    for msg in reversed(result["messages"]):
        if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
            answer = msg.content
            break
    return answer, None

st.set_page_config(page_title="Multi-Agent Assistant", page_icon="🤖")

st.title("🤖 Multi-Agent Assistant")
st.caption("Primary Assistant automatically routes: FAQ, Ticket Support, IT Support, Booking, or Web Search.")

# ---------- Initialize graph (Once per session) ----------
@st.cache_resource
def get_app():
    return build_graph()

app = get_app()

# ---------- Sidebar ----------
with st.sidebar:
    st.header("Settings")
    if "user_name" not in st.session_state:
        st.session_state.user_name = "Alice"
    user_name_input = st.text_input("Your name", value=st.session_state.user_name)
    if user_name_input != st.session_state.user_name:
        agent_logger.info(
            f"USER_SWITCH old={st.session_state.user_name!r} new={user_name_input!r} "
            f"-> forcing new thread (was {st.session_state.get('thread_id')})"
        )
        st.session_state.user_name = user_name_input
        st.session_state.thread_id = f"session-{uuid.uuid4().hex[:8]}"
        st.session_state.chat_history = []
        st.session_state.user_email = ""
        st.session_state.pending_action = None
        st.rerun()

    user_name = st.session_state.user_name
    
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = f"session-{uuid.uuid4().hex[:8]}"

    st.caption(f"🧵 Current thread: `{st.session_state.thread_id}`")

    if st.button("➕ New Chat", use_container_width=True):
        st.session_state.thread_id = f"session-{uuid.uuid4().hex[:8]}"
        st.session_state.chat_history = []
        st.session_state.pending_action = None
        # KHÔNG reset user_email/user_name -> user_id giữ nguyên, chỉ đổi thread_id
        st.rerun()

    thread_id = st.session_state.thread_id

    st.divider()
    st.subheader("Context (Optional)")
    user_email_input = st.text_input(
        "Email",
        value=st.session_state.get("user_email", ""),
        placeholder="you@example.com",
        help="Optional: provide your email to help the assistant give more personalized responses.",
    )
    if user_email_input:
        st.session_state.user_email = user_email_input
        db.upsert_conversation_context(thread_id, user_name, user_email_input)
        st.caption(f"✅ Saving context: `{user_email_input}`")
    elif st.session_state.get("user_email"):
        st.caption(f"✅ Saving context: `{st.session_state.user_email}` (from previous input)")

    st.divider()
    if st.button("🗑️ Delete Chat History"):
        st.session_state.chat_history = []
        st.session_state.user_email = ""
        st.rerun()

    st.divider()
    st.subheader("⚠️ Delete all Memory")
    st.caption("Delete Working (current), Semantic (facts learned), "
            "and Episodic (past experiences) memory of the user.")

    if st.button("🗑️ Delete all Memory", type="primary"):
        # config = {"configurable": {"thread_id": thread_id}}

        clear_working_memory(thread_id)
        clear_facts(user_name)
        clear_episodes(user_name)

        new_thread_id = f"session-{uuid.uuid4().hex[:8]}"
        st.session_state.chat_history = []
        st.session_state.user_email = ""
        st.session_state.pending_action = None

        st.success("All memory (Working + Semantic + Episodic) has been deleted.")
        st.rerun()

    st.divider()
    st.caption(f"🔒 Human-in-the-Loop: {'On' if HITL_ENABLED else 'Off'} "
            f"(Use the `HITL_ENABLED` environment variable in the `.env` file instead.)")

# ---------- Initialize the chat history ----------
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# ---------- Display chat history ----------
for msg in st.session_state.chat_history:
    role = "user" if msg["role"] == "user" else "assistant"
    with st.chat_message(role):
        st.markdown(msg["content"])
        # if msg.get("route"):
        #     st.caption(f"🔀 Route: `{msg['route']}`")

# ---------- Input ----------
query = st.chat_input("Enter your question...")

if query:
    st.session_state.chat_history.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.markdown(query)

    with st.chat_message("assistant"):
        with st.spinner("Processing..."):
            config = {"configurable": {"thread_id": thread_id}}

            invoke_input = {
                "messages": [HumanMessage(content=query)],
                "user_name": user_name,
                "thread_id": thread_id,
            }
            if st.session_state.get("user_email"):
                invoke_input["user_email"] = st.session_state.user_email

            result = app.invoke(invoke_input, config=config)
            answer, pending = process_graph_result(result, config)

            if pending:
                st.session_state.pending_action = pending
            else:
                st.markdown(answer)
                if result.get("route"):
                    st.caption(f"🔀 Route: `{result['route']}`")
                st.session_state.chat_history.append(
                    {"role": "assistant", "content": answer, "route": result.get("route", "")}
                )

if st.session_state.get("pending_action"):
    pending = st.session_state.pending_action
    config = {"configurable": {"thread_id": pending["thread_id"]}}

    st.warning("⏸️ Confirmation is required before execution.:")
    for tc in pending["tool_calls"]:
        st.code(f"{tc['name']}({tc['args']})", language="python")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Agree (Continue)", key=f"approve_{pending['thread_id']}"):
            result = approve_action(app, config)
            answer, new_pending = process_graph_result(result, config)

            if new_pending:
                st.session_state.pending_action = new_pending
            else:
                st.session_state.chat_history.append({"role": "assistant", "content": answer})
                st.session_state.pending_action = None
            st.rerun()

    with col2:
        if st.button("❌ Reject (Cancel)", key=f"reject_{pending['thread_id']}"):
            result = reject_action(app, config, pending["node"], pending["tool_calls"])
            answer, new_pending = process_graph_result(result, config)

            if new_pending:
                st.session_state.pending_action = new_pending
            else:
                st.session_state.chat_history.append({"role": "assistant", "content": answer})
                st.session_state.pending_action = None
            st.rerun()