from langchain.messages import HumanMessage, AIMessage

from graph import build_graph

app = build_graph()

config = {
    "configurable": {
        "thread_id": "alice-chat"
    }
}


def main():
    print("Type 'exit' or 'quit' to quit.\n")

    user_email = input("Email (Optional): ").strip()

    while True:
        query = input("Ask something: ")

        if query.lower() in {"exit", "quit"}:
            break

        invoke_input = {
            "messages": [HumanMessage(content=query)],
            "user_name": "Alice",
        }
        if user_email:
            invoke_input["user_email"] = user_email

        result = app.invoke(invoke_input, config=config)

        # context_node can automatically detect a new email address if the user enters it in the chat.
        if result.get("user_email"):
            user_email = result["user_email"]

        for msg in reversed(result["messages"]):
            if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
                print(f"Assistant: {msg.content}")
                break


if __name__ == "__main__":
    main()
