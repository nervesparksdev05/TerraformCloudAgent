import React, { useState } from 'react';
import { FileText, Download, Edit2, Check, X, RefreshCw, Save } from 'lucide-react';

/**
 * CodeEditor — shows a Terraform file with an inline edit mode.
 * Props:
 *   fileName   string
 *   content    string
 *   isLoading  bool
 *   onChange   (newContent: string) => void   — called when user saves edits
 */
export const CodeEditor = ({ fileName, content, isLoading, onChange }) => {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');

  const handleEdit = () => {
    setDraft(content || '');
    setEditing(true);
  };

  const handleSave = () => {
    onChange?.(draft);
    setEditing(false);
  };

  const handleCancel = () => {
    setEditing(false);
    setDraft('');
  };

  const handleDownload = () => {
    const blob = new Blob([content || ''], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = fileName;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold flex items-center gap-2 text-gray-300">
          <FileText size={15} />
          {fileName}
        </h3>
        <div className="flex items-center gap-2">
          {editing ? (
            <>
              <button
                onClick={handleSave}
                className="flex items-center gap-1 px-3 py-1 rounded-lg text-xs font-semibold bg-green-600/20 text-green-400 hover:bg-green-600/30 transition-all border border-green-600/30"
              >
                <Check size={12} /> Save
              </button>
              <button
                onClick={handleCancel}
                className="flex items-center gap-1 px-3 py-1 rounded-lg text-xs font-semibold bg-white/5 text-gray-400 hover:bg-white/10 transition-all border border-white/10"
              >
                <X size={12} /> Cancel
              </button>
            </>
          ) : (
            <>
              <button
                onClick={handleEdit}
                disabled={isLoading || !content}
                className="flex items-center gap-1 px-3 py-1 rounded-lg text-xs font-semibold bg-indigo-600/20 text-indigo-400 hover:bg-indigo-600/30 transition-all border border-indigo-600/30 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Edit2 size={12} /> Edit
              </button>
              <button
                onClick={handleDownload}
                disabled={!content}
                className="p-1.5 rounded-lg text-gray-500 hover:text-gray-300 hover:bg-white/5 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                title="Download file"
              >
                <Download size={14} />
              </button>
            </>
          )}
        </div>
      </div>

      {/* Content */}
      {editing ? (
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          className="w-full code-block resize-none font-mono text-xs text-gray-200 bg-black/30 border border-indigo-500/40 rounded-xl p-4 focus:outline-none focus:border-indigo-500 transition-all"
          style={{ minHeight: '320px', height: `${Math.max(320, (draft.split('\n').length + 2) * 18)}px` }}
          spellCheck={false}
          autoFocus
        />
      ) : (
        <pre className="code-block">
          {content ? content : (
            <div className="text-gray-400/50 italic py-4 text-center">
              {isLoading ? (
                <span className="flex items-center justify-center gap-2">
                  <RefreshCw size={14} className="animate-spin" /> Fetching content...
                </span>
              ) : `No content found for ${fileName}`}
            </div>
          )}
        </pre>
      )}
    </div>
  );
};

export default CodeEditor;
