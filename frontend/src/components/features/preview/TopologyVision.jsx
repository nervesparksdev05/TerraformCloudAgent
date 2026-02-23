import React, { useEffect, useRef, useState } from 'react';
import { Card } from '../../common';
import { HelpCircle, Info } from 'lucide-react';

const LEGEND_DATA = [
  { 
    title: 'Cloud Region', 
    meaning: 'The geographic location of your servers. Closer = faster for your users.' 
  },
  { 
    title: 'Load Balancer', 
    meaning: 'Think of this as a traffic controller. It distributes users across multiple servers to prevent crashes.' 
  },
  { 
    title: 'Virtual VM/Compute', 
    meaning: 'The actual computer(s) where your code runs. "t3.small" is like a basic laptop in the cloud.' 
  },
  { 
    title: 'Managed Database', 
    meaning: 'The vault for your data. Managed means the cloud provider handles backups and security updates.' 
  },
  { 
    title: 'Elastic Cache', 
    meaning: 'A high-speed storage layer to make your app respond instantly to repeat requests.' 
  },
  { 
    title: 'Private Subnet', 
    meaning: 'A secure zone with no direct internet access, protecting your database from hackers.' 
  }
];

export const TopologyVision = ({ params }) => {
  const containerRef = useRef(null);
  const [svgContent, setSvgContent] = useState('');
  const [error, setError] = useState(null);

  const generateMermaidString = () => {
    const provider = params?.cloud_provider?.toUpperCase() || 'CLOUD';
    const env = params?.environment?.toUpperCase() || 'APP';
    const isMultiInstance = (params?.instance_count || 1) > 1;
    const hasDB = params?.has_database;
    const hasCache = params?.has_cache;

    const appNodes = isMultiInstance
      ? 'VM1["Server 1"]\n        VM2["Server 2"]'
      : 'VM1["Application Server"]';

    const dataNodes = [
      hasDB ? `DB[("${params?.database_type || 'Database'}")]` : '',
      hasCache ? `Cache[("${params?.cache_type || 'Cache'}")]` : '',
    ]
      .filter(Boolean)
      .join('\n        ');

    return `graph TB
    subgraph VPC ["${provider} VPC (${env})"]
      direction TB
      LB[("Load Balancer")]
      subgraph AppTier ["Application Servers"]
        ${appNodes}
      end
      ${dataNodes ? `subgraph DataTier ["Secure Data Tier"]\n        ${dataNodes}\n      end` : ''}
      LB --> AppTier
      ${dataNodes ? 'AppTier --> DataTier' : ''}
    end
    classDef default fill:#111,stroke:#333,stroke-width:1px,color:#fff;
    classDef highlight fill:#582fb2,stroke:#8b5cf6,stroke-width:2px,color:#fff;
    class LB,VM1,VM2,DB,Cache highlight;`;
  };

  useEffect(() => {
    let cancelled = false;

    const renderDiagram = async () => {
      try {
        const mermaid = (await import('mermaid')).default;
        mermaid.initialize({
          startOnLoad: false,
          theme: 'dark',
          securityLevel: 'loose',
          fontFamily: 'Inter, sans-serif',
        });

        const chart = generateMermaidString();
        const uniqueId = `topology-${Date.now()}`;
        const { svg } = await mermaid.render(uniqueId, chart);

        if (!cancelled) {
          setSvgContent(svg);
          setError(null);
        }
      } catch (err) {
        console.error('Mermaid render error:', err);
        if (!cancelled) {
          setError('Diagram could not be rendered.');
        }
      }
    };

    renderDiagram();
    return () => { cancelled = true; };
  }, [params]);

  return (
    <Card className="p-0 border-white/10 overflow-hidden bg-black/40 backdrop-blur-md">
      <div className="flex flex-col md:flex-row">
        {/* Left: Diagram Area */}
        <div className="flex-1 p-6 relative min-h-[400px] flex items-center justify-center border-b md:border-b-0 md:border-r border-white/10">
          <div className="absolute top-4 left-4 flex items-center gap-2 text-xs font-medium text-purple-400 bg-purple-500/10 px-2 py-1 rounded-full border border-purple-500/20">
            <Info size={14} /> LIVE TOPOLOGY PREVIEW
          </div>

          <div ref={containerRef} className="w-full flex items-center justify-center">
            {error ? (
              <p className="text-red-400 text-sm italic">{error}</p>
            ) : svgContent ? (
              <div
                className="w-full"
                dangerouslySetInnerHTML={{ __html: svgContent }}
              />
            ) : (
              <div className="flex flex-col items-center gap-3 text-gray-500 text-sm">
                <div className="animate-spin w-8 h-8 rounded-full border-2 border-purple-500 border-t-transparent" />
                Rendering diagram…
              </div>
            )}
          </div>
        </div>

        {/* Right: Manual Guide (The "Legend") */}
        <div className="w-full md:w-80 bg-white/5 p-6 space-y-4">
          <h5 className="flex items-center gap-2 text-sm font-bold text-white mb-4">
            <HelpCircle size={16} className="text-purple-400" /> 
            Deployment Guide
          </h5>
          <div className="space-y-4 max-h-[400px] overflow-y-auto pr-2 custom-scrollbar">
            {LEGEND_DATA.filter(item => {
              if (item.title === 'Load Balancer' && !(params?.instance_count > 1)) return false;
              if (item.title === 'Managed Database' && !params?.has_database) return false;
              if (item.title === 'Elastic Cache' && !params?.has_cache) return false;
              return true;
            }).map((item, idx) => (
              <div key={idx} className="space-y-1">
                <span className="text-[10px] font-bold text-purple-400 uppercase tracking-wider">{item.title}</span>
                <p className="text-xs text-gray-400 leading-relaxed">{item.meaning}</p>
              </div>
            ))}
          </div>
          <div className="pt-4 mt-4 border-t border-white/10 text-[10px] text-gray-500 italic">
            This diagram shows how your code, data, and users will interact in the cloud.
          </div>
        </div>
      </div>
    </Card>
  );
};

export default TopologyVision;
