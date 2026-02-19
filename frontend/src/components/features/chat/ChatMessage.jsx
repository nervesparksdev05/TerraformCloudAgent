import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Star } from 'lucide-react';
import { Button } from '../../common';

export const ChatMessage = ({ message, index, sessionId, onSuggestionClick, onFeedback }) => {
  const isUser = message.role === 'user';
  const [rating, setRating] = useState(0);       // submitted rating (1-5)
  const [hoverRating, setHoverRating] = useState(0); // hover preview

  const handleRate = (value) => {
    if (rating) return; // already rated
    setRating(value);
    onFeedback?.(sessionId, index, value);
  };

  return (
    <div className={`flex flex-col ${isUser ? 'items-end' : 'items-start'} mb-4`}>
      <div className={`message ${isUser ? 'message-user' : 'message-bot'} ${message.isStreaming ? 'streaming' : ''}`}>
        {isUser ? (
          <div className="whitespace-pre-wrap">{message.content}</div>
        ) : (
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              code({ node, inline, className, children, ...props }) {
                const match = /language-(\w+)/.exec(className || '');
                return !inline ? (
                  <pre className="bg-black/30 rounded-lg p-3 overflow-x-auto my-2">
                    <code className={className} {...props}>
                      {children}
                    </code>
                  </pre>
                ) : (
                  <code className="bg-white/10 px-1.5 py-0.5 rounded text-sm font-mono" {...props}>
                    {children}
                  </code>
                );
              },
              a({ children, href, ...props }) {
                return (
                  <a
                    href={href}
                    className="text-purple-400 hover:text-purple-300 underline"
                    target="_blank"
                    rel="noopener noreferrer"
                    {...props}
                  >
                    {children}
                  </a>
                );
              },
              ul({ children, ...props }) {
                return <ul className="list-disc list-inside my-2 space-y-1" {...props}>{children}</ul>;
              },
              ol({ children, ...props }) {
                return <ol className="list-decimal list-inside my-2 space-y-1" {...props}>{children}</ol>;
              },
              p({ children, ...props }) {
                return <p className="my-2 leading-relaxed" {...props}>{children}</p>;
              },
              h1({ children, ...props }) {
                return <h1 className="text-2xl font-bold my-3" {...props}>{children}</h1>;
              },
              h2({ children, ...props }) {
                return <h2 className="text-xl font-bold my-2" {...props}>{children}</h2>;
              },
              h3({ children, ...props }) {
                return <h3 className="text-lg font-semibold my-2" {...props}>{children}</h3>;
              },
              blockquote({ children, ...props }) {
                return (
                  <blockquote className="border-l-4 border-purple-500 pl-4 py-1 my-2 italic text-gray-300" {...props}>
                    {children}
                  </blockquote>
                );
              },
              table({ children, ...props }) {
                return (
                  <div className="overflow-x-auto my-2">
                    <table className="min-w-full border border-white/10" {...props}>
                      {children}
                    </table>
                  </div>
                );
              },
              th({ children, ...props }) {
                return (
                  <th className="border border-white/10 px-3 py-2 bg-white/5 font-semibold text-left" {...props}>
                    {children}
                  </th>
                );
              },
              td({ children, ...props }) {
                return (
                  <td className="border border-white/10 px-3 py-2" {...props}>
                    {children}
                  </td>
                );
              },
            }}
          >
            {message.content}
          </ReactMarkdown>
        )}

        {/* Streaming indicator */}
        {message.isStreaming && (
          <span className="inline-block w-2 h-4 bg-purple-500 ml-1 animate-pulse"></span>
        )}
      </div>

      {/* Star rating (bot messages only, after streaming complete) */}
      {!isUser && !message.isStreaming && message.content && (
        <div className="flex items-center gap-1 mt-1.5 ml-1">
          {[1, 2, 3, 4, 5].map((star) => {
            const active = star <= (hoverRating || rating);
            return (
              <button
                key={star}
                onClick={() => handleRate(star)}
                onMouseEnter={() => !rating && setHoverRating(star)}
                onMouseLeave={() => !rating && setHoverRating(0)}
                disabled={!!rating}
                className={`p-0.5 rounded transition-all duration-150 ${rating
                    ? active
                      ? 'text-yellow-400'
                      : 'text-gray-700'
                    : active
                      ? 'text-yellow-400 scale-110'
                      : 'text-gray-600 hover:text-yellow-300'
                  } ${rating ? 'cursor-default' : 'cursor-pointer'}`}
                title={`Rate ${star} star${star > 1 ? 's' : ''}`}
              >
                <Star size={16} fill={active ? 'currentColor' : 'none'} />
              </button>
            );
          })}
          {rating > 0 && (
            <span className="text-xs text-gray-500 ml-1.5 animate-fade-in">
              {rating >= 4 ? '🎉 Thanks!' : rating >= 2 ? 'Noted, thanks!' : 'Sorry, we\'ll improve!'}
            </span>
          )}
        </div>
      )}

      {/* Suggestions */}
      {!isUser && message.suggestions?.length > 0 && !message.isStreaming && (
        <div className="flex flex-wrap gap-2 mt-2 max-w-[80%]">
          {message.suggestions.slice(0, 4).map((suggestion, idx) => (
            <button
              key={idx}
              className="px-3 py-1.5 rounded-lg border border-white/10 text-xs text-gray-400 hover:bg-white/5 hover:border-purple-500/50 transition-all"
              onClick={() => onSuggestionClick(suggestion)}
            >
              {suggestion}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

export default ChatMessage;
