import React from 'react';
import { Plus, Terminal, LogOut, MessageSquare, FileCode, LayoutDashboard } from 'lucide-react';
import { Card, Button } from '../common';
import { SessionItem } from '../features/sessions';

export const Sidebar = ({ 
  sessions, 
  activeSessionId, 
  onNewChat, 
  onSessionSelect, 
  onSessionDelete,
  userEmail,
  onLogout,
  activeTab,
  onTabChange,
  hasRun
}) => {
  return (
    <aside className="sidebar">
      <Card gradient className="mb-6">
        <h2 className="flex items-center gap-2 text-white">
          <Terminal size={24} /> TCA
        </h2>
        <p className="text-xs text-white/80 mt-1">README-driven Cloud Agent</p>
      </Card>

      <Button variant="primary" className="w-full mb-6" onClick={onNewChat} icon={Plus}>
        New Chat
      </Button>

      {activeSessionId && (
        <div className="mb-6">
          <h3 className="text-xs uppercase tracking-wider text-gray-500 mb-2 px-2">
            Current Session
          </h3>
          <div className="space-y-1">
            <button
              onClick={() => onTabChange && onTabChange('chat')}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === 'chat' 
                  ? 'bg-white/10 text-white' 
                  : 'text-gray-400 hover:text-white hover:bg-white/5'
              }`}
            >
              <MessageSquare size={18} />
              Conversation
            </button>
            
            {hasRun && (
              <>
                <button
                  onClick={() => onTabChange && onTabChange('review')}
                  className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    activeTab === 'review' 
                      ? 'bg-white/10 text-white' 
                      : 'text-gray-400 hover:text-white hover:bg-white/5'
                  }`}
                >
                  <FileCode size={18} />
                  File Review
                </button>
                <button
                  onClick={() => onTabChange && onTabChange('manage')}
                  className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    activeTab === 'manage' 
                      ? 'bg-white/10 text-white' 
                      : 'text-gray-400 hover:text-white hover:bg-white/5'
                  }`}
                >
                  <LayoutDashboard size={18} />
                  Lifecycle
                </button>
              </>
            )}
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto pr-2">
        <h3 className="text-xs uppercase tracking-wider text-gray-500 mb-4 px-2">
          Recent Deployments
        </h3>
        {sessions.map((session) => (
          <SessionItem
            key={session.session_id}
            session={session}
            isActive={activeSessionId === session.session_id}
            onClick={() => onSessionSelect(session.session_id)}
            onDelete={() => onSessionDelete(session.session_id)}
          />
        ))}
      </div>

      <div className="mt-auto pt-6 border-t border-white/5">
        <div
          className="flex items-center gap-3 p-3 rounded-xl hover:bg-white/5 cursor-pointer text-gray-500 hover:text-white transition-all"
          onClick={onLogout}
        >
          <LogOut size={18} />
          <span className="text-sm font-medium">Log out</span>
        </div>
        <div className="mt-4 px-2">
          <p className="text-[10px] text-gray-500 truncate">{userEmail}</p>
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
