class ChatManager:
    chat_history = {}
    def __init__(self):
        pass

    @classmethod
    def update_chat_history(obj, last_message, session_id):
        obj.chat_history[session_id].append(last_message)

    @classmethod
    def get_chat_history(obj, session_id):
        return obj.chat_history[session_id]
    