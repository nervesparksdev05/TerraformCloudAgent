import React, { useState } from 'react';
import { ChatPanel } from '../components/features/chat';
import { CodeEditor } from '../components/features/chat';
import { Card, Button, Badge } from '../components/common';
import {
  Play,
  Mail,
  AlertCircle,
  Trash,
  LayoutDashboard,
  Wand2,
  Save,
  RefreshCw,
} from 'lucide-react';
import { api } from '../services/api';

const FILE_KEYS = ['main_tf', 'variables_tf', 'outputs_tf'];

export const WorkspacePage = ({
  sessionId,
  messages,
  inputMessage,
  onInputChange,
  onSendMessage,
  isComplete,
  collectedParams,
  runId,
  runData,
  runFiles,
  onGenerateTerraform,
  onFetchRunData,
  githubRepo,
  activeTab,
  onTabChange,
}) => {
  // Local editable copies of the files
  const [editedFiles, setEditedFiles] = useState({});
  const [hasUnsaved, setHasUnsaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');

  // AI feedback panel
  const [feedback, setFeedback] = useState('');
  const [regenerating, setRegenerating] = useState(false);
  const [regenError, setRegenError] = useState('');

  // Merge server files with local edits
  const files = { ...runFiles, ...editedFiles };

  const handleFileChange = (key, newContent) => {
    setEditedFiles((prev) => ({ ...prev, [key]: newContent }));
    setHasUnsaved(true);
    setSaveError('');
  };

  const handleSaveFiles = async () => {
    setSaving(true);
    setSaveError('');
    try {
      await api.updateRunFiles(runId, files);
      setEditedFiles({});
      setHasUnsaved(false);
      await onFetchRunData(runId);
    } catch (err) {
      setSaveError(err.response?.data?.detail || err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleAIRegenerate = async () => {
    if (!feedback.trim()) return;
    setRegenerating(true);
    setRegenError('');
    try {
      await api.editRunWithFeedback(runId, feedback);
      setFeedback('');
      setEditedFiles({});
      setHasUnsaved(false);
      // Poll until planning is done
      await onFetchRunData(runId);
    } catch (err) {
      setRegenError(err.response?.data?.detail || err.message);
    } finally {
      setRegenerating(false);
    }
  };

  const handleAction = async (actionFn, id, successMsg) => {
    try {
      await actionFn(id);
      alert(successMsg);
      onFetchRunData(id);
    } catch (err) {
      alert('Action failed: ' + err.message);
    }
  };

  const canEdit = runData && ['planned', 'reviewing'].includes(runData.status);

  return (
    <>
      <header
        className="flex items-center justify-between px-8 border-b border-white/5"
        style={{ height: 'var(--header-height)' }}
      >
        <div className="flex items-center gap-4">
          <h2 className="text-lg font-semibold">{githubRepo || 'Deployment Session'}</h2>
          <div className="flex gap-1">
            <button
              className={`px-4 py-1.5 rounded-full text-xs font-semibold transition-all ${
                activeTab === 'chat'
                  ? 'bg-primary-gradient text-white'
                  : 'text-gray-500 hover:text-gray-300'
              }`}
              onClick={() => onTabChange('chat')}
              style={activeTab === 'chat' ? { background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' } : {}}
            >
              Conversation
            </button>
            {runId && (
              <>
                <button
                  className={`px-4 py-1.5 rounded-full text-xs font-semibold transition-all ${
                    activeTab === 'review'
                      ? 'bg-primary-gradient text-white'
                      : 'text-gray-500 hover:text-gray-300'
                  }`}
                  onClick={() => onTabChange('review')}
                  style={activeTab === 'review' ? { background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' } : {}}
                >
                  File Review
                  {hasUnsaved && <span className="ml-1.5 w-1.5 h-1.5 rounded-full bg-yellow-400 inline-block" />}
                </button>
                <button
                  className={`px-4 py-1.5 rounded-full text-xs font-semibold transition-all ${
                    activeTab === 'manage'
                      ? 'bg-primary-gradient text-white'
                      : 'text-gray-500 hover:text-gray-300'
                  }`}
                  onClick={() => onTabChange('manage')}
                  style={activeTab === 'manage' ? { background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' } : {}}
                >
                  Lifecycle
                </button>
              </>
            )}
          </div>
        </div>

        {runData && (
          <Badge
            variant={
              runData.status === 'completed' || runData.status === 'applied'
                ? 'success'
                : 'warning'
            }
          >
            <div
              className={`w-2 h-2 rounded-full animate-pulse ${
                runData.status === 'completed' || runData.status === 'applied'
                  ? 'bg-green-500'
                  : 'bg-yellow-500'
              }`}
            />
            {runData.status}
          </Badge>
        )}
      </header>

      <div className="flex-1 flex overflow-hidden">
        {activeTab === 'chat' && (
          <ChatPanel
            messages={messages}
            inputMessage={inputMessage}
            onInputChange={onInputChange}
            onSendMessage={onSendMessage}
            isComplete={isComplete}
            collectedParams={collectedParams}
            onGenerateTerraform={onGenerateTerraform}
            runId={runId}
          />
        )}

        {activeTab === 'review' && (
          <div className="flex-1 flex flex-col p-8 overflow-y-auto gap-8">
            {!runData || runData.status === 'planning' ? (
              <div className="flex items-center justify-center h-full">
                <div className="text-center space-y-4">
                  <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-500 mx-auto" />
                  <p className="text-gray-400">Generating Terraform configuration...</p>
                  <p className="text-sm text-gray-500">This usually takes 10–20 seconds</p>
                </div>
              </div>
            ) : (
              <>
                {/* ── Toolbar ── */}
                <div className="flex items-center justify-between">
                  <h3 className="text-lg font-semibold text-gray-300">Terraform Configuration</h3>
                  <div className="flex items-center gap-3">
                    {(!runFiles || Object.keys(runFiles).length === 0) && (
                      <span className="text-xs text-yellow-500/70 italic flex items-center gap-2">
                        <AlertCircle size={14} /> Files are being synchronized...
                      </span>
                    )}
                    {hasUnsaved && (
                      <Button
                        variant="primary"
                        size="sm"
                        onClick={handleSaveFiles}
                        disabled={saving || !canEdit}
                        icon={saving ? RefreshCw : Save}
                        className={saving ? 'animate-pulse' : ''}
                      >
                        {saving ? 'Saving...' : 'Save Changes'}
                      </Button>
                    )}
                  </div>
                </div>

                {saveError && (
                  <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-xs">
                    {saveError}
                  </div>
                )}

                {!canEdit && runData && (
                  <div className="p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/20 text-yellow-400 text-xs flex items-center gap-2">
                    <AlertCircle size={14} />
                    Files can only be edited when the run is in <strong>planned</strong> or <strong>reviewing</strong> status.
                  </div>
                )}

                {/* ── File editors ── */}
                <div className="grid grid-cols-1 gap-8">
                  {FILE_KEYS.map((key) => (
                    <CodeEditor
                      key={key}
                      fileName={key.replace('_', '.')}
                      content={files[key]}
                      onChange={canEdit ? (val) => handleFileChange(key, val) : undefined}
                    />
                  ))}
                </div>

                {/* ── AI Feedback / Re-generate panel ── */}
                {canEdit && (
                  <Card className="space-y-4">
                    <div className="flex items-center gap-2">
                      <Wand2 size={18} className="text-indigo-400" />
                      <h4 className="font-semibold text-gray-200">AI Re-generation</h4>
                      <span className="text-xs text-gray-500">
                        Describe what to change and let the AI regenerate the files
                      </span>
                    </div>
                    <textarea
                      value={feedback}
                      onChange={(e) => setFeedback(e.target.value)}
                      placeholder='e.g. "Add an RDS instance with a private subnet" or "Change instance type to t3.medium"'
                      className="w-full bg-white/5 border border-white/10 rounded-xl p-4 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-indigo-500 transition-all resize-none"
                      rows={3}
                    />
                    {regenError && (
                      <div className="text-xs text-red-400">{regenError}</div>
                    )}
                    <Button
                      variant="primary"
                      onClick={handleAIRegenerate}
                      disabled={!feedback.trim() || regenerating}
                      icon={regenerating ? RefreshCw : Wand2}
                      className={regenerating ? 'animate-pulse' : ''}
                    >
                      {regenerating ? 'Regenerating...' : 'Regenerate with AI'}
                    </Button>
                  </Card>
                )}
              </>
            )}
          </div>
        )}

        {activeTab === 'manage' && (
          <div className="flex-1 p-8 overflow-y-auto">
            <div className="grid grid-cols-2 gap-8">
              <Card className="space-y-6">
                <h3 className="flex items-center gap-2 text-lg font-semibold">
                  <LayoutDashboard size={20} /> Operations
                </h3>
                <div className="space-y-4">
                  <Button
                    variant="primary"
                    className="w-full py-4"
                    onClick={() => handleAction(api.approveRun, runId, 'Deployment Approved')}
                    disabled={['applying', 'applied', 'completed'].includes(runData?.status)}
                    icon={Play}
                  >
                    Approve &amp; Deploy Stack
                  </Button>
                  <Button
                    variant="warning"
                    className="w-full py-4"
                    onClick={() => handleAction(api.sendForApproval, runId, 'Approval Email Sent')}
                    icon={Mail}
                  >
                    Request Remote Approval
                  </Button>
                  <div className="grid grid-cols-2 gap-4">
                    <Button
                      variant="danger"
                      size="md"
                      onClick={() => handleAction(api.rejectRun, runId, 'Plan Rejected')}
                      icon={AlertCircle}
                    >
                      Reject Plan
                    </Button>
                    <Button
                      variant="danger"
                      size="md"
                      onClick={() => handleAction(api.destroyRun, runId, 'Destroying Stack')}
                      icon={Trash}
                    >
                      Destroy
                    </Button>
                  </div>
                </div>
              </Card>

              <div className="space-y-8">
                <Card>
                  <h4 className="text-gray-400 text-xs uppercase tracking-widest mb-4">
                    Environment Context
                  </h4>
                  <div className="space-y-3">
                    {Object.entries(collectedParams).map(([key, value]) => (
                      <div
                        key={key}
                        className="flex justify-between items-center py-2 border-b border-white/5"
                      >
                        <span className="text-xs text-gray-500 capitalize">
                          {key.replace('_', ' ')}
                        </span>
                        <span className="text-xs font-semibold">{String(value)}</span>
                      </div>
                    ))}
                  </div>
                </Card>
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  );
};

export default WorkspacePage;
