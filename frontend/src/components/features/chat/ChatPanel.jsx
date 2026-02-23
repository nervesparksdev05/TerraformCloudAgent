import React, { useRef, useEffect } from 'react';
import { ChatMessage, ChatInput } from './';
import { Button, Card } from '../../common';
import { CheckCircle, Terminal } from 'lucide-react';

export const ChatPanel = ({
  messages,
  inputMessage,
  onInputChange,
  onSendMessage,
  isComplete,
  collectedParams,
  onGenerateTerraform,
  runId,
  sessionId,
}) => {
  const chatEndRef = useRef(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="flex-1 flex flex-col p-8 bg-transparent min-h-0">
      <div className="flex-1 overflow-y-auto mb-8 space-y-4 pr-4 min-h-0">
        {messages.map((message, index) => (
          <ChatMessage
            key={index}
            message={message}
            onSuggestionClick={onSendMessage}
            sessionId={sessionId}
          />
        ))}
        <div ref={chatEndRef} />
      </div>

      {isComplete && !runId && (
        <div className="mb-4 animate-fade-in space-y-4">
          <Card className="border-green-500/30 flex items-center justify-between">
            <div>
              <h4 className="flex items-center gap-2 text-green-500">
                <CheckCircle size={18} /> Requirements Captured
              </h4>
              <p className="text-sm text-gray-400 mt-1">
                Provider: {collectedParams.cloud_provider?.toUpperCase()}. Ready to build your
                cluster.
              </p>
            </div>
            <Button variant="primary" onClick={onGenerateTerraform} icon={Terminal}>
              Generate Infrastructure
            </Button>
          </Card>
        </div>
      )}

      {!isComplete && (
        <ChatInput
          value={inputMessage}
          onChange={(e) => onInputChange(e.target.value)}
          onSend={() => onSendMessage(inputMessage)}
          placeholder="Reply to the agent..."
        />
      )}
    </div>
  );
};

export default ChatPanel;
