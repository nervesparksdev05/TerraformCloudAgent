import React from 'react';
import { FileText, Download } from 'lucide-react';

export const CodeViewer = ({ fileName, content, isLoading }) => {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <FileText size={16} />
          {fileName}
        </h3>
        <button className="text-gray-500 hover:text-gray-300 transition-colors">
          <Download size={14} />
        </button>
      </div>
      <pre className="code-block">
        {content ? content : (
          <div className="text-gray-400/50 italic py-4 text-center">
            {isLoading ? 'Fetching content...' : `No content found for ${fileName}`}
          </div>
        )}
      </pre>
    </div>
  );
};

export default CodeViewer;
