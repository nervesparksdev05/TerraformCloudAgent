import React from 'react';
import MermaidDiagram from './MermaidDiagram';

export const InsightsPanel = ({
  topologyDiagram,
}) => {
  return (
    <div className="flex-1 p-8 overflow-y-auto w-full">
      <div className="max-w-6xl mx-auto space-y-8">
        
        {/* TOPOLOGY DIAGRAM */}
        <section>
          <div className="mb-4">
            <h2 className="text-xl font-bold text-white tracking-tight">Topology Vision</h2>
            <p className="text-sm text-gray-400 mt-1">
              Auto-generated architectural diagram of the planned infrastructure.
            </p>
          </div>
          <div className="bg-black/40 border border-indigo-500/20 rounded-xl p-4 md:p-8 min-h-[300px] flex items-center justify-center relative overflow-hidden">
            {/* Subtle glow */}
            <div className="absolute inset-x-0 bottom-0 h-40 bg-indigo-500/10 blur-3xl rounded-full" />
            
            {topologyDiagram ? (
              <div className="w-full relative z-10">
                <MermaidDiagram chart={topologyDiagram} />
              </div>
            ) : (
              <div className="text-gray-500 italic text-sm flex flex-col items-center">
                <div className="animate-pulse mb-3 w-12 h-12 rounded-full bg-white/5" />
                No topology diagram generated for this run.
              </div>
            )}
          </div>
        </section>

      </div>
    </div>
  );
};

export default InsightsPanel;
