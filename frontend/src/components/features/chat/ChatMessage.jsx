import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Star } from 'lucide-react';
import { api } from '../../../services/api';
import { Button } from '../../common';

export const ChatMessage = ({ message, onSuggestionClick, sessionId }) => {
  const isUser = message.role === 'user';
  const [rating, setRating] = useState(0);
  const [hoverRating, setHoverRating] = useState(0);
  const [submitted, setSubmitted] = useState(false);

  const handleRate = async (value) => {
    if (!sessionId || submitted) return;
    try {
      await api.submitFeedback(sessionId, value);
      setRating(value);
      setSubmitted(true);
    } catch (e) {
      console.error("Failed to submit feedback", e);
    }
  };

  return (
    <div className={`flex flex-col ${isUser ? 'items-end' : 'items-start'} mb-4`}>
      <div className={`message ${isUser ? 'message-user' : 'message-bot'} ${message.isStreaming ? 'streaming' : ''}`}>
        {isUser ? (
          // User messages - plain text
          <div className="whitespace-pre-wrap">{message.content}</div>
        ) : (
          // Bot messages - markdown formatted
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              // Preformatted blocks
              pre({ children, ...props }) {
                return (
                  <pre className="bg-black/30 rounded-lg p-3 overflow-x-auto my-2" {...props}>
                    {children}
                  </pre>
                );
              },
              // Code items
              code({ node, inline, className, children, ...props }) {
                return !inline ? (
                  <code className={`${className || ''} block font-mono text-sm`} {...props}>
                    {children}
                  </code>
                ) : (
                  <code className="bg-white/10 px-1.5 py-0.5 rounded text-sm font-mono" {...props}>
                    {children}
                  </code>
                );
              },
              // Links
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
              // Lists
              ul({ children, ...props }) {
                return <ul className="list-disc list-inside my-2 space-y-1" {...props}>{children}</ul>;
              },
              ol({ children, ...props }) {
                return <ol className="list-decimal list-inside my-2 space-y-1" {...props}>{children}</ol>;
              },
              // Paragraphs
              p({ children, ...props }) {
                return <p className="my-2 leading-relaxed" {...props}>{children}</p>;
              },
              // Headings
              h1({ children, ...props }) {
                return <h1 className="text-2xl font-bold my-3" {...props}>{children}</h1>;
              },
              h2({ children, ...props }) {
                return <h2 className="text-xl font-bold my-2" {...props}>{children}</h2>;
              },
              h3({ children, ...props }) {
                return <h3 className="text-lg font-semibold my-2" {...props}>{children}</h3>;
              },
              // Blockquotes
              blockquote({ children, ...props }) {
                return (
                  <blockquote className="border-l-4 border-purple-500 pl-4 py-1 my-2 italic text-gray-300" {...props}>
                    {children}
                  </blockquote>
                );
              },
              // Tables
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

      {/* Feedback Stars */}
      {!isUser && !message.isStreaming && sessionId && (
        <div className="flex items-center gap-2 mt-1 px-2">
          {submitted ? (
            <span className="text-xs text-green-400">Thanks for your feedback!</span>
          ) : (
            <div className="flex items-center" onMouseLeave={() => setHoverRating(0)}>
              {[1, 2, 3, 4, 5].map((star) => (
                <Star
                  key={star}
                  size={14}
                  className={`cursor-pointer transition-colors ${(hoverRating || rating) >= star ? 'text-yellow-400 fill-yellow-400' : 'text-gray-500'
                    }`}
                  onMouseEnter={() => setHoverRating(star)}
                  onClick={() => handleRate(star)}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Suggestions */}
      {!isUser && message.suggestions?.length > 0 && !message.isStreaming && (
        <div className="flex flex-wrap gap-2 mt-2 max-w-[80%]">
          {message.suggestions.slice(0, 4).map((suggestion, index) => (
            <button
              key={index}
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
