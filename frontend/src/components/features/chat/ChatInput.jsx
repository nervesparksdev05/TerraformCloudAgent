import React from 'react';
import { Input, Button } from '../../common';
import { Send } from 'lucide-react';

export const ChatInput = ({ value, onChange, onSend, placeholder = 'Type a message...' }) => {
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  return (
    <div className="relative mt-auto">
      <Input
        type="text"
        placeholder={placeholder}
        value={value}
        onChange={onChange}
        onKeyDown={handleKeyDown}
        className="pr-16"
      />
      <button
        className="absolute right-3 top-2 bottom-2 aspect-square rounded-xl flex items-center justify-center text-white"
        style={{ background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' }}
        onClick={onSend}
      >
        <Send size={18} />
      </button>
    </div>
  );
};

export default ChatInput;
