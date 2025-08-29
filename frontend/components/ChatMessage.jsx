// components/ChatMessage.jsx
export default function ChatMessage({ role, content }) {
    const isUser = role === "user";
    return (
      <div className={`flex ${isUser ? "justify-end" : "justify-start"} my-1`}>
        <div
          className={`max-w-[80%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm border ${
            isUser
              ? "bg-blue-600/20 text-blue-100 border-blue-700"
              : "bg-[var(--panel-2)] text-slate-100 border-slate-700"
          }`}
        >
          {content || ""}
        </div>
      </div>
    );
  }