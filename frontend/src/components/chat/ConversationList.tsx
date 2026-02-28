import type { Conversation } from '../../types';

interface ConversationListProps {
  conversations: Conversation[];
  activeConversationId?: string;
  onSelectConversation: (conversationId: string) => void;
  onDeleteConversation: (conversationId: string) => void;
  onNewConversation: () => void;
}

export function ConversationList({
  conversations,
  activeConversationId,
  onSelectConversation,
  onDeleteConversation,
  onNewConversation,
}: ConversationListProps) {
  return (
    <aside className="w-full md:w-64 lg:w-72 bg-white border-r border-gray-200 flex-shrink-0 flex flex-col">
      <div className="p-4 border-b border-gray-200">
        <button
          onClick={onNewConversation}
          className="w-full brand-gradient text-white py-2 px-4 rounded-lg hover:opacity-90 transition-opacity font-medium"
        >
          New Chat
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {conversations.length === 0 ? (
          <div className="p-4 text-gray-500 text-sm">No conversations yet</div>
        ) : (
          <div className="p-2">
            {conversations.map((conversation) => (
              <div
                key={conversation.id}
                className={`group relative p-3 rounded-lg cursor-pointer mb-2 transition-colors ${
                  activeConversationId === conversation.id
                    ? 'bg-gradient-to-r from-[#00E5FF]/10 to-[#FF00E5]/10 border border-[#00E5FF]/30'
                    : 'hover:bg-gray-50'
                }`}
                onClick={() => onSelectConversation(conversation.id)}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <h3 className="font-medium text-sm text-gray-900 truncate">
                      {conversation.title}
                    </h3>
                    {conversation.last_message_preview && (
                      <p className="text-xs text-gray-500 truncate mt-1">
                        {conversation.last_message_preview}
                      </p>
                    )}
                    <p className="text-xs text-gray-400 mt-1">
                      {new Date(conversation.updated_at).toLocaleDateString()}
                    </p>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeleteConversation(conversation.id);
                    }}
                    className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-500 transition-opacity"
                    aria-label="Delete conversation"
                  >
                    <svg
                      className="w-4 h-4"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                      />
                    </svg>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}
