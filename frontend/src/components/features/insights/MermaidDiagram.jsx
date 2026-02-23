import React, { useEffect, useRef, useState } from 'react';
import mermaid from 'mermaid';

mermaid.initialize({
  startOnLoad: false,
  theme: 'base',
  themeVariables: {
    fontFamily: 'ui-sans-serif, system-ui, sans-serif',
    primaryColor: '#4f46e5',
    primaryTextColor: '#fff',
    primaryBorderColor: '#4338ca',
    lineColor: '#6366f1',
    secondaryColor: '#1e1b4b',
    tertiaryColor: '#312e81',
    edgeLabelBackground: '#00000000',
  },
  securityLevel: 'loose',
});

/**
 * Sanitize LLM-generated Mermaid code before rendering.
 * Fixes the most common parse failures caused by LLM output:
 *   - \n (escape sequence) inside node label brackets → replaced with space
 *   - subgraph / direction / end blocks → stripped (flat graphs only)
 */
function sanitizeMermaid(code) {
  if (!code) return code;

  // 1. Remove literal \n escape sequence inside QUOTED labels
  //    e.g. LB["Global LB\n(main)"] → LB["Global LB (main)"]
  code = code.replace(/("(?:[^"\\]|\\.)*?")/g, (match) =>
    match.replace(/\\n/g, ' ')
  );

  // 2. Remove literal \n inside UNQUOTED bracket labels
  //    e.g. LB[Global LB\n(main)] → LB[Global LB (main)]
  code = code.replace(/(\[[^\]"]*?)\\n([^\]]*?\])/g, '$1 $2');

  // 3. Strip subgraph declarations + their direction and end lines
  code = code.replace(/^\s*subgraph\s+[^\n]*/gm, '');
  code = code.replace(/^\s*(?:direction\s+\w+|end)\s*$/gm, '');

  // 4. Collapse extra blank lines
  code = code.replace(/\n{3,}/g, '\n\n');

  return code.trim();
}

export const MermaidDiagram = ({ chart }) => {
  const containerRef = useRef(null);
  const [svgContent, setSvgContent] = useState('');
  const [error, setError] = useState(null);

  useEffect(() => {
    let isMounted = true;
    
    const renderDiagram = async () => {
      if (!chart || !containerRef.current) return;
      
      try {
        setError(null);
        const sanitized = sanitizeMermaid(chart);
        const id = `mermaid-${Date.now()}-${Math.floor(Math.random() * 10000)}`;
        const { svg } = await mermaid.render(id, sanitized);
        
        if (isMounted) {
          setSvgContent(svg);
        }
      } catch (err) {
        console.error('Mermaid render error:', err);
        if (isMounted) {
          setError(err.message || 'Failed to render diagram');
          setSvgContent('');
        }
      }
    };

    renderDiagram();

    return () => {
      isMounted = false;
    };
  }, [chart]);

  if (!chart) {
    return <div className="text-gray-500 italic text-sm">No diagram data available</div>;
  }

  if (error) {
    return (
      <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm overflow-auto">
        <strong>Diagram Render Error:</strong>
        <pre className="mt-2 text-xs opacity-80 whitespace-pre-wrap">{error}</pre>
        <div className="mt-4 pt-4 border-t border-red-500/20">
          <strong>Raw content:</strong>
          <pre className="mt-2 text-xs opacity-60 whitespace-pre-wrap">{chart}</pre>
        </div>
      </div>
    );
  }

  return (
    <div 
      className="mermaid-container flex justify-center w-full overflow-x-auto p-4 [&>svg]:max-w-full [&>svg]:h-auto"
      ref={containerRef}
      dangerouslySetInnerHTML={{ __html: svgContent }}
    />
  );
};

export default MermaidDiagram;
