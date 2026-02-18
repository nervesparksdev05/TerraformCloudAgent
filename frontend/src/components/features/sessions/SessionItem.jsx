import React from 'react';
import { Github, Trash2 } from 'lucide-react';

export const SessionItem = ({ session, isActive, onClick, onDelete }) => {
  return (
    <div
      className={`flex items-center gap-3 p-3 rounded-xl mb-2 cursor-pointer transition-all ${
        isActive ? 'bg-white/10 active-session' : 'hover:bg-white/5'
      }`}
      onClick={onClick}
    >
      <div className="p-2 rounded-lg bg-white/5">
        <Github size={16} className="text-gray-400" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{session.repo || 'Untitled'}</p>
        <p className="text-[10px] text-gray-500 truncate uppercase">
          {session.provider || 'Unset'}
        </p>
      </div>
      <button
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
        className="p-1 hover:text-red-500 text-gray-500 transition-colors"
      >
        <Trash2 size={14} />
      </button>
    </div>
  );
};

export default SessionItem;
