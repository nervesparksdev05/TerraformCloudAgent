import React from 'react';
import { Card } from '../../common';
import { AlertTriangle, Lightbulb, CheckCircle2, Info } from 'lucide-react';

export const SelfHealerAlert = ({ diagnosis }) => {
  if (!diagnosis) return null;

  const { diagnosis: text, action_type, suggested_fix, confidence } = diagnosis;
  const isAutoFix = action_type === 'auto_fix';

  return (
    <Card className={`border-l-4 ${isAutoFix ? 'border-indigo-500' : 'border-yellow-500'} bg-black/40 backdrop-blur-md animate-fade-in`}>
      <div className="flex items-start gap-4">
        <div className={`p-2 rounded-lg ${isAutoFix ? 'bg-indigo-500/10 text-indigo-400' : 'bg-yellow-500/10 text-yellow-400'}`}>
          {isAutoFix ? <Lightbulb size={24} /> : <AlertTriangle size={24} />}
        </div>
        
        <div className="flex-1 space-y-3">
          <div>
            <div className="flex items-center justify-between">
              <h4 className="font-bold text-white text-lg">Autonomous Diagnostic Result</h4>
              {confidence && (
                <span className="text-[10px] bg-white/5 px-2 py-0.5 rounded text-gray-500 uppercase tracking-widest">
                  Confidence: {Math.round(confidence * 100)}%
                </span>
              )}
            </div>
            <p className="text-gray-300 mt-1 leading-relaxed">
              {text}
            </p>
          </div>

          <div className="bg-white/5 rounded-xl p-4 border border-white/5">
            <h5 className="flex items-center gap-2 text-sm font-bold text-white mb-2 uppercase tracking-tight">
              {isAutoFix ? (
                <>
                  <CheckCircle2 size={16} className="text-indigo-400" /> 
                  Proposed Code Fix
                </>
              ) : (
                <>
                  <Info size={16} className="text-yellow-400" /> 
                  Required Manual Action
                </>
              )}
            </h5>
            <div className="text-sm text-gray-400 bg-black/30 rounded-lg p-3 font-mono overflow-x-auto">
              {suggested_fix}
            </div>
          </div>

          {isAutoFix && (
            <p className="text-[10px] text-gray-500 italic">
              Tip: You can go to the "File Review" tab and paste this code to fix the issue.
            </p>
          )}
        </div>
      </div>
    </Card>
  );
};

export default SelfHealerAlert;
